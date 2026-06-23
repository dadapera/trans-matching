from __future__ import annotations

import time
from typing import Literal

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from trans_matching.agent.callbacks import AgentTraceCallback
from trans_matching.agent.context import MatchSession, reset_session, set_session
from trans_matching.agent.router import classify_card_transaction
from trans_matching.agent.tools import (
    AGENT_TOOLS,
    build_result_from_output,
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
1. Se la transazione è Expedia (EG*TRVL) → usa search_expedia, poi search_gestionale o compare_amount.
2. Se è MSC (mscbook.it / MSC Cruises) → usa search_msc, poi search_gestionale.
3. Se l'importo potrebbe essere suddiviso su più righe → usa check_sum.
4. Per casi generici → search_gestionale interpretando codici fornitore e COGNOME/NOME nelle descrizioni SIAP.
5. Prima di concludere con importi diversi → compare_amount.

Regole confidenza:
- "alto": match univoco e coerente (ospite/fornitore/data/importo).
- "medio": match probabile con lieve scostamento importo o dati parziali.
- "basso": incerto, ambiguo, o troppi candidati equivalenti.

Non usare confidence alto/medio se restano alternative equivalenti: elencale in alternatives.
Se non c'è evidenza sufficiente, lascia identificativi vuoti e confidence basso.

Formati gestionale: identificativo|data|importo|descrizione (es. RYA RYANAIR COGNOME/NOME)."""


def get_matching_agent():
    global _MATCHING_AGENT
    if _MATCHING_AGENT is None:
        config = get_openai_config()
        llm = ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=0,
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

        user_prompt = _format_user_prompt(session, category)
        session.logger.log(
            "txn_start",
            trace_id=session.trace_id,
            row_number=session.row_number,
            card_date=session.card.date,
            card_amount=str(session.card.amount),
            card_description=session.card.description,
            category=category,
        )

        callback = AgentTraceCallback()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_prompt}]},
            config={
                "callbacks": [callback],
                "recursion_limit": agent_config.max_iterations * 2,
            },
        )

        output = _extract_structured_output(result)
        alternatives = [
            MatchAlternative(
                identificativi=item.identificativi,
                confidence=item.confidence,
                reason=item.reason,
                gestionale_preview=preview_for_identificativi(session.pool, item.identificativi),
            )
            for item in output.alternatives
        ]
        agent_result = build_result_from_output(
            card=session.card,
            trace_id=session.trace_id,
            row_number=session.row_number,
            strategy=output.strategy or category,
            identificativi=output.identificativi,
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


def _format_user_prompt(session: MatchSession, category: str) -> str:
    return f"""Abbina questa transazione carta a righe del gestionale.

Transazione carta:
- data: {session.card.date}
- importo: {session.card.amount}
- descrizione: {session.card.description}
- categoria suggerita: {category}

Gestionale disponibile (identificativo|data|importo|descrizione):
{session.pool.format_rows()}

Finestra date suggerita: ±{session.date_window_days} giorni.
Restituisci identificativi (1 o più), confidence, reason, alternatives se ambiguo."""


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
