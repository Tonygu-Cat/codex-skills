You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task.

Start with a section titled "Direction card". Copy the task's latest Direction card verbatim: the newest <direction_card> block in this conversation, or the "## Direction card" section of its canonical handoff document. If the user changed direction after that card was written, keep the card and add the change, quoting the user's words, directly below it. If there is no card, write "Direction card: none" and state the user's current goal in one sentence, quoting their words.

Then include:
- The canonical handoff document path and revision, if there is one
- Current progress and key decisions, quoting the user's own words for decisions
- Work in progress: the unfinished step; background jobs with command, PID, output path and whether they are still running; uncommitted workspace changes; external apps or sessions left running
- Important context, constraints, or user preferences
- What remains to be done: the next exact actions, and anything the user still has to do
- Any critical data, examples, or references needed to continue

Do not add goals, scope or plans the user did not approve. Be concise, structured, and focused on helping the next LLM seamlessly continue the work.
