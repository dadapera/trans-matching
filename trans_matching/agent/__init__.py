"""Agent matching package.

Heavy imports (pipeline / LLM) stay in submodules so lightweight imports
like pool/tools helpers do not pull OpenSSL on Windows.
"""

__all__ = ["run_agent_matching"]


def __getattr__(name: str):
    if name == "run_agent_matching":
        from trans_matching.agent.pipeline import run_agent_matching

        return run_agent_matching
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
