## Prose in comments, Javadoc, and commit messages

Keep sentences structurally simple; the content is already hard enough.

- **Finite verbs, not participles.** No trailing `-ing` clauses hung off a comma
  ("..., rejecting a non-empty sub-list") and no absolutes ("..., an absent
  sub-list read as empty"). Give the idea its own sentence with a real subject
  and verb.
- **Verb early.** If more than ~4 words separate the sentence start from its
  verb, restructure. Heavy subjects with embedded relative clauses ("A
  non-empty sub-list for a kind the dialect does not allow fails validation")
  make the reader hold everything in suspense.
- **Active voice, real actor as subject.** Name who does the thing.
- **One idea per sentence.** Three short sentences beat one with three clauses.
- **Disambiguate overloaded domain words.** If a term has two senses in this
  codebase, qualify it or pick another word.
- **Fact first, reason second.** Lead with what holds at this spot in the code,
  then explain why. "This method checks neither X nor Y. A dialect decides X."
  beats the same two facts in the opposite order.

Content rules:

- Document what the reader needs at the point of use. Rationale for designs
  that were *not* chosen belongs in the commit message, not the type.
- Don't enumerate field or method names the comment doesn't own — they go stale.
- In Javadoc, `-` renders as a hyphen, not a dash. Use a period or semicolon.
