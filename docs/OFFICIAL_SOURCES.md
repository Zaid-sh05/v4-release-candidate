# Official Jordanian source map

Verified/curated for Qanoni Pilot V3 on 2026-08-19.

Qanoni treats government pages as legal-source inputs, but it distinguishes between a page that merely references a law and a canonical copy of the law text.

## Central legislation and gazette

- Legislation and Opinion Bureau (ديوان التشريع والرأي): https://lob.gov.jo/?lang=ar&v=1
  - Central legislation service. In this pilot it remains `reference_only` until a dedicated connector is implemented for the dynamic legislation interface.
- Prime Ministry Official Gazette: https://www.pm.gov.jo/ar/Pages/NewsPaper
  - Freshness source for newly published laws, amendments and regulations.

## Justice and court procedure

V3 also uses official Ministry of Justice service pages as operational evidence for criminal appeals, civil appeals, and complaints before the Public Prosecution. These service pages complement statutes; they do not replace the consolidated legal code.

- Ministry of Justice laws: https://www.moj.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
- Ministry of Justice court services confirm the current governing references used by the pilot:
  - Penal Code No. 16 of 1960 and amendments.
  - Criminal Procedure Law No. 9 of 1961 and amendments.
  - Civil Procedure Law No. 24 of 1988 and amendments.
  - Civil Code No. 43 of 1976 and amendments.

## Personal status and Sharia

- Chief Islamic Justice Department laws: https://sjd.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
  - Personal Status Law No. 15 of 2019.
  - Sharia procedure, Sharia enforcement and later amendments.

## Traffic and cybercrime

- Public Security Directorate laws: https://psd.gov.jo/ar-jo/%D8%A7%D9%84%D9%85%D8%AD%D8%AA%D9%88%D9%89/%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86/
- Jordan Traffic Institute legislation: https://www.psd.gov.jo/ar-jo/%D8%A7%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D9%88%D8%AD%D8%AF%D8%A7%D8%AA/%D8%A7%D9%84%D9%85%D8%B9%D9%87%D8%AF-%D8%A7%D9%84%D9%85%D8%B1%D9%88%D8%B1%D9%8A-%D8%A7%D9%84%D8%A3%D8%B1%D8%AF%D9%86%D9%8A/%D8%A7%D9%84%D8%AA%D8%B4%D8%B1%D9%8A%D8%B9%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D8%A5%D8%B5%D8%AF%D8%A7%D8%B1%D8%A7%D8%AA/
  - Traffic Law No. 49 of 2008 and amendments.
  - Traffic-points system.
- Official Gazette issue containing Cybercrime Law No. 17 of 2023 and Traffic Law amendment No. 18 of 2023: https://pm.gov.jo/Ar/Pages/NewsPaperDetails/5874

## Labor, companies and data protection

- Ministry of Labour laws: https://mol.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
- Companies Control Department laws: https://ccd.gov.jo/Ar/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
- Ministry of Digital Economy and Entrepreneurship legislation: https://www.modee.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86_%D9%88%D8%A7%D9%84%D8%A3%D9%86%D8%B8%D9%85%D8%A9_%D9%88_%D8%A7%D9%84%D8%AA%D8%B9%D9%84%D9%8A%D9%85%D8%A7%D8%AA_%D8%A7%D9%84%D8%B5%D8%A7%D8%AF%D8%B1%D8%A9_%D8%A8%D9%85%D9%82%D8%AA%D8%B6%D8%A7%D9%87

## Additional official government law hosts

These are registered as secondary official-government hosts for extracting base texts. They do not replace Gazette/LOB verification of amendments.

- Ministry of Health hosted law copies: https://moh.gov.jo/ar/Tafeileh/InfoPageDaynamic/172/562
  - Includes hosted copies of the Civil Code, Penal Code and Labour Law.
- Ministry of Social Development laws: https://mosd.gov.jo/Ar/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
  - Includes Penal Code No. 16 of 1960 and amendments among its published legislation.
- Ministry of Local Administration laws: https://www.mola.gov.jo/Ar/Pages/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86
  - Lists the Civil Code No. 43 of 1976 and other laws.

## Quality rule

A source can be official and still be unsuitable as a current consolidated text. Qanoni therefore records source type and coverage state instead of treating every government PDF as the final current version.
