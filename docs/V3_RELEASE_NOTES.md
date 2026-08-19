# Qanoni Pilot V3 release notes

## User-facing improvements

- Penalty questions now lead with the penalty when the retrieved official text actually states it.
- Appeal/challenge deadline questions lead with the duration and, when supported, the date/event from which it is counted.
- Court-fee questions lead with the supported amount and scope.
- Complaint/appeal questions lead with the operational procedure instead of a source dump.
- Judgment-finality questions refuse to generalize when the judgment type, challenge route or service rules are not proved by the retrieved text.
- Labor-rights output prefers curated official service/guidance facts over unreadable PDF text layers.
- Source cards are fully clickable and open the official source.
- Suggested pilot questions include deadlines, Public Prosecution complaints and criminal appeal fees.
- No emojis/emoticons in assistant output.

## Retrieval/routing improvements

- Added stronger Jordanian Arabic intent detection for penalty, deadline, appeal, complaint, fees, judgment, enforcement, procedure and rights.
- Added criminal-procedure vocabulary including جزائي/جزائية/جنائي/جنائية.
- Added conduct guards so unrelated Penal Code amendments do not appear as evidence merely because they contain generic punishment words.
- Added stronger ranking for official court-service and official-guidance material.
- Added focused excerpts around matched legal terms.

## Curated official pilot facts

V3 includes compact verified operational facts for:
- Ministry of Justice criminal appeal service.
- Ministry of Justice complaint to Public Prosecution service.
- Ministry of Justice civil appeal service.
- Supreme Judge Department Sharia appeal guidance.
- Ministry of Labour basic worker-rights FAQ.
- Ministry of Labour Article 31 service.

## Known gaps

The shipped pilot does not claim a complete consolidated article-by-article copy of every Jordanian statute. In particular, full consolidated local text remains incomplete for the Penal Code, Civil Code, Criminal Procedure and Civil Procedure. V3 exposes those gaps instead of fabricating answers.
