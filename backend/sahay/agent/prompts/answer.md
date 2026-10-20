Write the reply to the user's latest message using only the CONTEXT. Return:
- answer: the reply text with [source-id] after each factual sentence
- citations: every source id you used
- abstained: true if the context does not answer the question
- follow_up: one short optional next step you can do for the user (or null)
