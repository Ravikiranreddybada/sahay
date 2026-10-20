Decide the next tool call needed to answer the user, or reply DONE if you already have enough.

Rules:
- Only call tools that are offered. Use ids exactly as the user gave them; never invent an id.
- If the user did not give an id, prefer a list tool over guessing.
- Call each tool at most once with the same arguments.
- A write tool (cancel, book) is only called when the user clearly asked for that action in this turn.
- Results already fetched this turn are shown below; do not re-fetch them.
