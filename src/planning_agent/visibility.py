"""Prompt-pattern helpers for surfacing observations in-flow.

Observations are soft inferences. Any prompt that exposes them
to the planning agent must require that the agent *names* the
observation when it drives a decision, so the user can veto in
the moment. M-R2/M-R3/M-R4 embed the rendered section into
their system prompts.
"""

VISIBILITY_INSTRUCTION = """\
When you use an observation below to inform a scheduling
decision, name the observation explicitly in your reasoning.
For example: "Scheduling the gutter clean Saturday morning —
observation has you avoiding outdoor tasks after 5pm in fall,
push back if wrong." This lets the user veto a bad inference
in the moment rather than having to audit a file later.
Observations are soft — they do not override rules or
explicit user statements.
"""


def render_observations_section(observations_body: str) -> str:
    """Build the observations section for a system prompt.

    Returns an empty string when there are no observations,
    so prompts can unconditionally interpolate the result.
    """
    if not observations_body.strip():
        return ""
    return (
        "## Observations\n\n"
        f"{VISIBILITY_INSTRUCTION}\n"
        f"{observations_body}"
    )
