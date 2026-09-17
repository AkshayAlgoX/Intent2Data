# Canonical Demo Candidates

## Category Q1: Obvious Mapping
*Purpose: Demonstrate baseline functionality with straightforward lexical matches.*

### Candidate 1.1
1. **Exact research question:** "How does current smoking status relate to self-reported health?"
2. **Dataset:** Health and Retirement Study (HRS)
3. **Relevant concept(s):** Smoking status, self-reported general health.
4. **Expected role(s):** Exposure (smoking), Outcome (self-reported health).
5. **Why it is suitable for the demo:** Everyone understands the variables. 
6. **Why it demonstrates Intent2Data:** Shows basic role decomposition (exposure vs outcome).
7. **Expected module/structural behavior:** Readily found in standard health modules (`core::C` or `core::B`).
8. **Known limitation/risk:** Too simple; a standard keyword search also finds these.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Low.

### Candidate 1.2
1. **Exact research question:** "Does years of education predict household income?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Education level, total household income.
4. **Expected role(s):** Exposure (education), Outcome (income).
5. **Why it is suitable for the demo:** Very standard econometric analysis.
6. **Why it demonstrates Intent2Data:** Validates demographic extraction.
7. **Expected module/structural behavior:** Found in demographic and financial sections.
8. **Known limitation/risk:** Income variables can be heavily imputed/complex to merge.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Low.

### Candidate 1.3
1. **Exact research question:** "Is there a relationship between age and retirement status?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Age, retirement.
4. **Expected role(s):** Exposure (age), Outcome (retirement).
5. **Why it is suitable for the demo:** Trivial to verify.
6. **Why it demonstrates Intent2Data:** Basic temporal/demographic extraction.
7. **Expected module/structural behavior:** Core tracker and employment modules.
8. **Known limitation/risk:** Does not showcase the LLM's advanced reasoning.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Very Low.


## Category Q2: Non-Obvious Structural Mapping
*Purpose: Demonstrate where standard retrieval fails and LLM module context succeeds.*

### Candidate 2.1
1. **Exact research question:** "How does lifelong religious and spiritual involvement shape physical functioning in later life?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Religious involvement, physical functioning.
4. **Expected role(s):** Exposure (religion), Outcome (physical functioning).
5. **Why it is suitable for the demo:** "Religion" is structurally localized to specific modules, and the question asks for "lifelong/childhood" specifics.
6. **Why it demonstrates Intent2Data:** A generic search for "religion" returns hundreds of generic beliefs. Intent2Data grabs the module `2016_core::V` and uses the LLM to surgically extract variables like "HOW OFTEN ATTEND SERVICES DURING CHILDHOOD".
7. **Expected module/structural behavior:** LLM parses the `core::V` codebook to find temporal variants.
8. **Known limitation/risk:** None, it's a proven success case.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Medium.

### Candidate 2.2
1. **Exact research question:** "Does pre-pandemic functional impairment predict survival outcomes after COVID-19?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Functional impairment (ADLs), COVID-19 infection, survival/mortality.
4. **Expected role(s):** Exposure (functional impairment), Outcome (survival), Covariate (COVID-19 timing).
5. **Why it is suitable for the demo:** "Survival" does not map lexically to standard survey variables.
6. **Why it demonstrates Intent2Data:** Standard search for "survival" misses `EXDEATHYR` (Year of Death). Intent2Data retrieves the `tracker::TR` module and uses the LLM to deduce that "Year of Death" and "Vital Status" perfectly operationalize survival.
7. **Expected module/structural behavior:** LLM cross-references the tracker module for mortality variables.
8. **Known limitation/risk:** The COVID-19 temporal logic adds complexity.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Medium.

### Candidate 2.3
1. **Exact research question:** "How do childhood socioeconomic conditions affect late-life cognitive decline?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Childhood SES, cognitive decline.
4. **Expected role(s):** Exposure (Childhood SES), Outcome (cognitive decline), Temporal (late-life).
5. **Why it is suitable for the demo:** "Childhood SES" is a latent concept.
6. **Why it demonstrates Intent2Data:** The LLM must deduce that parental education (e.g., "FATHER EDUCATION- HIGHEST GRADE") and childhood financial status are the correct proxies for SES.
7. **Expected module/structural behavior:** Pulls from family structure and childhood history modules.
8. **Known limitation/risk:** Requires strong proxy reasoning.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** High.

### Candidate 2.4
1. **Exact research question:** "Is neighborhood social cohesion related to cardiovascular health?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Neighborhood cohesion, cardiovascular health.
4. **Expected role(s):** Exposure (neighborhood cohesion), Outcome (heart conditions).
5. **Why it is suitable for the demo:** "Cardiovascular health" maps to specific conditions (heart attack, stroke, hypertension) rather than a single "health" variable.
6. **Why it demonstrates Intent2Data:** Shows how Intent2Data decomposes a broad medical category into specific operationalized survey questions inside the health modules.
7. **Expected module/structural behavior:** Explores the physical health `core::C` module for specific diagnoses.
8. **Known limitation/risk:** The list of cardiovascular conditions can be extensive.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Medium.

### Candidate 2.5
1. **Exact research question:** "Does exposure to job stress over generations affect memory?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Job stress, memory.
4. **Expected role(s):** Exposure (job stress), Outcome (memory).
5. **Why it is suitable for the demo:** Job stress requires specific occupational module retrieval.
6. **Why it demonstrates Intent2Data:** Highlights the need for the LLM to scan occupational/employment modules and extract subjective stress variables, differentiating them from physical job demands.
7. **Expected module/structural behavior:** Requires retrieval of the employment/retirement modules.
8. **Known limitation/risk:** "Generations" aspect might be difficult to satisfy strictly with HRS data.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** High.


## Category Q3: Honest Limitation
*Purpose: Show the system's guardrails, transparency, and acknowledgement of missing data or retrieval boundaries.*

### Candidate 3.1
1. **Exact research question:** "How do epigenetic aging clocks (like GrimAge) correlate with daily smartphone usage in older adults?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Epigenetic aging (GrimAge), smartphone usage.
4. **Expected role(s):** Exposure (smartphone usage), Outcome (epigenetic aging).
5. **Why it is suitable for the demo:** HRS may have some genetic/biomarker data, but "smartphone usage" or specific clock markers might be completely absent or extremely sparse.
6. **Why it demonstrates Intent2Data:** The Operationalization Validator should flag "smartphone usage" as missing or unmeasured, rather than hallucinating a proxy.
7. **Expected module/structural behavior:** Fails to retrieve a valid module for smartphone usage.
8. **Known limitation/risk:** The system might accidentally proxy it to "internet usage".
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Low risk of hallucination if validator works.

### Candidate 3.2
1. **Exact research question:** "Does localized air pollution (PM2.5) exposure drive early-onset dementia?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Air pollution, dementia.
4. **Expected role(s):** Exposure (pollution), Outcome (dementia).
5. **Why it is suitable for the demo:** HRS does not contain detailed geospatial PM2.5 tracking natively in the public use file (it requires restricted geographic data merges).
6. **Why it demonstrates Intent2Data:** The system will correctly identify dementia variables but must state that air pollution requires restricted contextual data linking.
7. **Expected module/structural behavior:** Retrieves cognition modules, but fails to find environmental modules.
8. **Known limitation/risk:** A great way to explain data governance/linking limits.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** Medium.

### Candidate 3.3
1. **Exact research question:** "Is the balance between monocytes and protective cholesterol predicting survival?"
2. **Dataset:** HRS
3. **Relevant concept(s):** Monocytes, protective cholesterol (HDL), survival.
4. **Expected role(s):** Exposure (Biomarkers), Outcome (Survival).
5. **Why it is suitable for the demo:** Very specific biomarkers. If the module retrieval step (BM25) fails to rank the specific biomarker module in the Top 10, the LLM will miss it (the known 0.698 reachability ceiling).
6. **Why it demonstrates Intent2Data:** Perfectly illustrates the "Module Retrieval Reachability" bottleneck. If the keyword "monocytes" doesn't hit a module document strongly enough, the system honestly reports it cannot find the exposure variables.
7. **Expected module/structural behavior:** Tests the limits of the initial BM25 module embedding.
8. **Known limitation/risk:** Shows a genuine algorithmic limitation of the current v1 pipeline.
9. **Safe to use publicly:** Yes.
10. **Complexity/risk rating:** High.

