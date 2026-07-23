from __future__ import annotations

import time
from typing import Literal

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from trans_matching.agent.callbacks import AgentTraceCallback
from trans_matching.agent.context import MatchSession, reset_session, set_session
from trans_matching.agent.rate_limit import invoke_with_rate_limit_retry
from trans_matching.agent.router import classify_card_transaction
from trans_matching.agent.tools import (
    AGENT_TOOLS,
    build_result_from_output,
    clean_identificativi,
    collect_document_group_context,
    collect_expedia_context,
    collect_msc_context,
    preview_for_identificativi,
)
from trans_matching.config import get_agent_config, get_openai_config
from trans_matching.matchers.agent_models import AgentMatchResult, MatchAlternative
from trans_matching.models import Transaction
from trans_matching.openai_http import (
    build_openai_async_http_client,
    build_openai_http_client,
)

_MATCHING_AGENT = None


class AlternativeOutput(BaseModel):
    identificativi: list[str] = Field(default_factory=list)
    confidence: Literal["alto", "medio", "basso"]
    reason: str = ""


class AgentMatchOutput(BaseModel):
    identificativi: list[str] = Field(
        default_factory=list,
        description="Identificativi righe gestionale SIAP abbinate (1 o più per multi-voce)",
    )
    confidence: Literal["alto", "medio", "basso"]
    reason: str = Field(description="Motivazione breve del match o mancato match")
    alternatives: list[AlternativeOutput] = Field(
        default_factory=list,
        description="Altri candidati plausibili se il match è incerto",
    )
    strategy: Literal["expedia", "msc", "sum", "gestionale", "generic"] = "generic"


_SYSTEM_PROMPT = """Sei un agente contabile che abbina transazioni carta di credito Amex a righe del gestionale SIAP.

Obiettivo: trovare il match più plausibile usando i tool disponibili.

Workflow consigliato:
1. Se la transazione è Expedia (EG*TRVL) → il nome ospite/passeggero dall'email è il riferimento PRINCIPALE per la ricerca.
   Parti dai candidati gestionale del contesto Expedia; hotel e importo sono solo supporti secondari.
   Decidi TU se i nomi coincidono: nel SIAP possono essere troncati, abbreviati o con ordine nome/cognome invertito — usa il giudizio, non un match letterale.
   Le pratiche possono avere più righe SIAP, storni o importi non identici: restituisci più identificativi solo se il gruppo ha lo stesso ospite (coerente a tuo giudizio).
   VIETATO: scegliere una riga SIAP solo perché l'importo è simile se i nomi indicano chiaramente persone diverse. In quel caso lascia identificativi vuoti (confidence basso).
2. Se è MSC (mscbook.it / MSC Cruises) → il backend estrae i cognomi passeggeri dagli allegati; non cercare match gestionale.
3. Se l'importo potrebbe essere suddiviso su più righe dello stesso Documento+Codice Cliente → usa check_document_group_sum.
4. Se resta una somma multi-riga non coperta dal documento → usa check_sum.
5. Per casi generici → interpreta direttamente le righe gestionale in context, usando codici fornitore e COGNOME/NOME nelle descrizioni SIAP.
6. Prima di concludere con importi diversi → compare_amount.

Regole confidenza:
- "alto": match univoco e coerente (ospite/fornitore/data/importo). Per Expedia l'ospite deve essere lo stesso a tuo giudizio (anche se troncato o invertito).
- "medio": match probabile con lieve scostamento importo o dati parziali. Per Expedia l'ospite deve comunque risultare la stessa persona.
- "basso": incerto, ambiguo, troppi candidati equivalenti, oppure (Expedia) ospite assente o chiaramente diverso.

Non usare confidence alto/medio se restano alternative equivalenti: elencale in alternatives.
Per Expedia non usare confidence alto/medio se i nomi indicano persone diverse, anche se l'importo è vicino.
Se non c'è evidenza sufficiente, lascia identificativi vuoti e confidence basso.

Formati gestionale: identificativo|data|importo|descrizione  [available]
Puoi riusare la stessa pratica/riga SIAP su più transazioni quando l'evidenza lo giustifica; l'ambiguità sarà evidenziata nel report per revisione umana."""


def get_matching_agent():
    global _MATCHING_AGENT
    if _MATCHING_AGENT is None:
        config = get_openai_config()
        agent_config = get_agent_config()
        llm = ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=0,
            max_retries=agent_config.rate_limit_max_retries,
            http_client=build_openai_http_client(),
            http_async_client=build_openai_async_http_client(),
        )
        _MATCHING_AGENT = create_agent(
            llm,
            tools=AGENT_TOOLS,
            system_prompt=_SYSTEM_PROMPT,
            response_format=AgentMatchOutput,
        )
    return _MATCHING_AGENT


def match_one(session: MatchSession) -> AgentMatchResult:
    category = classify_card_transaction(session.card.description)
    session.logger.log(
        "router_classify",
        trace_id=session.trace_id,
        category=category,
        description=session.card.description,
    )

    token = set_session(session)
    started = time.perf_counter()
    try:
        agent_config = get_agent_config()
        agent = get_matching_agent()

        session.logger.log(
            "txn_start",
            trace_id=session.trace_id,
            row_number=session.row_number,
            card_date=session.card.date,
            card_amount=str(session.card.amount),
            card_description=session.card.description,
            category=category,
        )
        expedia_context = (
            collect_expedia_context(session) if category == "expedia" else None
        )
        if category == "msc":
            msc_context = collect_msc_context(session)
            surnames = msc_context.get("passenger_surnames", [])
            surnames_text = ", ".join(surnames) if surnames else "non trovati"
            agent_result = AgentMatchResult(
                card=session.card,
                matched=False,
                confidence="basso",
                reason=f"MSCBOOK: cognomi passeggeri {surnames_text}. Match gestionale non eseguito.",
                strategy="msc",
                trace_id=session.trace_id,
                row_number=session.row_number,
                metadata={"msc": msc_context},
            )
            session.logger.log(
                "txn_end",
                trace_id=session.trace_id,
                matched=False,
                confidence=agent_result.confidence,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return agent_result
        document_group_context = collect_document_group_context(session)
        user_prompt = _format_user_prompt(
            session,
            category,
            expedia_context,
            document_group_context,
        )

        callback = AgentTraceCallback()
        invoke_config = {
            "callbacks": [callback],
            "recursion_limit": agent_config.max_iterations * 2,
        }

        def _invoke_agent():
            return agent.invoke(
                {"messages": [{"role": "user", "content": user_prompt}]},
                config=invoke_config,
            )

        result = invoke_with_rate_limit_retry(
            _invoke_agent,
            max_retries=agent_config.rate_limit_max_retries,
            on_retry=lambda attempt, wait, exc: session.logger.log(
                "rate_limit_retry",
                trace_id=session.trace_id,
                attempt=attempt,
                wait_seconds=round(wait, 2),
                error=str(exc)[:200],
            ),
        )

        output = _extract_structured_output(result)
        alternatives = [
            _build_alternative(session, item)
            for item in output.alternatives
        ]
        agent_result = build_result_from_output(
            card=session.card,
            trace_id=session.trace_id,
            row_number=session.row_number,
            strategy=output.strategy or category,
            identificativi=clean_identificativi(output.identificativi),
            confidence=output.confidence,
            reason=output.reason,
            alternatives=alternatives,
            pool=session.pool,
        )

        session.logger.log(
            "confidence_gate",
            trace_id=session.trace_id,
            confidence=agent_result.confidence,
            matched=agent_result.matched,
            identificativi=[txn.identificativo for txn in agent_result.gestionale],
            alternatives=len(agent_result.alternatives),
        )
        session.logger.log(
            "txn_end",
            trace_id=session.trace_id,
            matched=agent_result.matched,
            confidence=agent_result.confidence,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return agent_result
    except Exception as exc:
        reason = str(exc)
        if "Connection error" in reason or exc.__class__.__name__ == "APIConnectionError":
            reason = (
                f"{reason}. Verifica rete/VPN; se SSL fallisce imposta "
                "OPENAI_VERIFY_SSL=false o OPENAI_CA_BUNDLE in .env"
            )
        elif "rate limit" in reason.lower() or "429" in reason:
            reason = (
                f"{reason}. Aumenta AGENT_TXN_DELAY_SECONDS (es. 1-2) "
                "o AGENT_RATE_LIMIT_MAX_RETRIES in .env"
            )
        session.logger.log_error("error", exc, trace_id=session.trace_id, phase="match_one")
        return AgentMatchResult(
            card=session.card,
            matched=False,
            confidence="basso",
            reason=f"Errore agente: {reason}",
            strategy=category,
            trace_id=session.trace_id,
            row_number=session.row_number,
        )
    finally:
        reset_session(token)


def _format_user_prompt(
    session: MatchSession,
    category: str,
    expedia_context: dict | None = None,
    document_group_context: dict | None = None,
) -> str:
    expedia_section = ""
    if expedia_context is not None:
        expedia_section = f"""
Contesto Expedia deterministico già raccolto prima dell'LLM:
{expedia_context}

Regola Expedia: il campo guest (nome passeggero) è il criterio primario.
Valuta tu se i nomi SIAP corrispondono allo stesso ospite (troncature, abbreviazioni, ordine nome/cognome invertito sono accettabili).
Preferisci gestionale_candidates se coerenti; non abbinare per sola similarità di importo se i nomi indicano persone diverse.
Split/storni ok solo se lo stesso ospite a tuo giudizio.
"""
    document_group_section = ""
    if document_group_context and document_group_context.get("count", 0) > 0:
        document_group_section = f"""
Candidati aggregati SIAP per stesso Documento+Codice Cliente:
{document_group_context}

Se un gruppo ha somma coerente, stesso fornitore/contesto e non ci sono alternative equivalenti, puoi restituire tutti i suoi identificativi.
"""

    return f"""Abbina questa transazione carta a righe del gestionale.

Transazione carta:
- data: {session.card.date}
- importo: {session.card.amount}
- descrizione: {session.card.description}
- categoria suggerita: {category}
{expedia_section}
{document_group_section}

Gestionale (tutte le righe; [available] o già abbinate):
{session.pool.format_rows()}

Finestra date suggerita: ±{session.date_window_days} giorni.
Puoi riusare una pratica SIAP già scelta per altre transazioni se è il match più plausibile.
Restituisci identificativi (1 o più), confidence, reason, alternatives se ambiguo."""


def _build_alternative(session: MatchSession, item: AlternativeOutput) -> MatchAlternative:
    identificativi = clean_identificativi(item.identificativi)
    preview = preview_for_identificativi(session.pool, identificativi)
    if not preview and item.reason:
        preview = item.reason
    return MatchAlternative(
        identificativi=identificativi,
        confidence=item.confidence,
        reason=item.reason,
        gestionale_preview=preview,
    )


def _extract_structured_output(result: dict) -> AgentMatchOutput:
    if "structured_response" in result and isinstance(result["structured_response"], AgentMatchOutput):
        return result["structured_response"]
    if "structured_response" in result and isinstance(result["structured_response"], dict):
        return AgentMatchOutput.model_validate(result["structured_response"])

    for key in ("output", "response", "final"):
        value = result.get(key)
        if isinstance(value, AgentMatchOutput):
            return value
        if isinstance(value, dict):
            try:
                return AgentMatchOutput.model_validate(value)
            except Exception:
                pass

    messages = result.get("messages") or []
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if isinstance(content, AgentMatchOutput):
            return content
        if isinstance(content, dict):
            try:
                return AgentMatchOutput.model_validate(content)
            except Exception:
                continue
        if isinstance(content, str):
            try:
                return AgentMatchOutput.model_validate_json(content)
            except Exception:
                continue

    raise ValueError("Risposta strutturata agente non trovata")
