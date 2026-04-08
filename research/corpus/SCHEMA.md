# MJPIS Global Prosecuted Cases Corpus — Schema Documentation

**Version**: 0.1
**Last Updated**: 2026-04-08
**Purpose**: Multi-jurisdiction prosecuted procurement fraud cases used for deriving the Multi-Jurisdiction Procurement Integrity Standard (MJPIS) statistical thresholds.

---

## Corpus Structure

### Top-Level Fields

```json
{
  "corpus_version": "0.1",
  "corpus_name": "MJPIS Global Prosecuted Cases Corpus",
  "description": "...",
  "last_updated": "2026-04-08",
  "jurisdictions_included": ["US_DOJ", "UK_SFO", "FR_PNF", "WB_INT"],
  "total_cases": 9,
  "cases": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `corpus_version` | string | Semantic version number (e.g., "0.1", "1.0") |
| `corpus_name` | string | Human-readable corpus name |
| `description` | string | Purpose and scope of the corpus |
| `last_updated` | string | ISO 8601 date of last corpus update |
| `jurisdictions_included` | array[string] | List of jurisdictions represented in corpus |
| `total_cases` | integer | Count of cases in the corpus |
| `cases` | array[object] | Array of case objects (see Case Schema below) |

---

## Case Schema

Each case object in the `cases` array follows this structure:

```json
{
  "case_id": "US_v_Oracle_2011",
  "jurisdiction": "US_DOJ",
  "jurisdiction_type": "federal_criminal",
  "country_code": "US",
  "year": 2011,
  "legal_basis": "False Claims Act - Price Inflation",
  "case_name": "United States v. Oracle Corporation",
  "contract_value_usd": 1270000000,
  "contract_value_local": 1270000000,
  "contract_currency": "USD",
  "settlement_amount_usd": 199500000,
  "markup_percentage": 350.0,
  "bribery_channel_amount_usd": null,
  "bribery_channel_percentage": null,
  "dimensional_tags": ["markup_based"],
  "evidentiary_standard": "beyond_reasonable_doubt",
  "source_url": "https://www.justice.gov/opa/pr/...",
  "source_document": "DOJ Press Release, 2011-08-01",
  "notes": "Failed to provide promised educational discounts..."
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| **`case_id`** | string | Yes | Stable unique identifier in snake_case format (e.g., `US_v_Oracle_2011`) |
| **`jurisdiction`** | string | Yes | Enforcing jurisdiction code (see Jurisdiction Codes below) |
| **`jurisdiction_type`** | string | Yes | Type of legal proceeding (see Jurisdiction Types below) |
| **`country_code`** | string | Yes | ISO 3166-1 alpha-2 code of enforcing country (e.g., "US", "GB", "FR") |
| **`year`** | integer | Yes | Year of settlement, sanction, or judgment |
| **`legal_basis`** | string | Yes | Statute or legal framework cited (e.g., "False Claims Act - Price Inflation") |
| **`case_name`** | string | Yes | Formal case name (e.g., "United States v. Oracle Corporation") |
| **`contract_value_usd`** | number/null | No | Original contract value converted to USD (null if unknown) |
| **`contract_value_local`** | number/null | No | Original contract value in local currency (null if unknown) |
| **`contract_currency`** | string | Yes | ISO 4217 currency code (e.g., "USD", "GBP", "EUR") |
| **`settlement_amount_usd`** | number/null | No | Settlement/penalty amount in USD (null if unknown) |
| **`markup_percentage`** | number/null | No | Documented markup above fair market value as percentage (null if not documented) |
| **`bribery_channel_amount_usd`** | number/null | No | Documented bribery intermediary payment in USD (null if not applicable) |
| **`bribery_channel_percentage`** | number/null | No | Bribery payment as percentage of contract value (null if not applicable) |
| **`dimensional_tags`** | array[string] | Yes | List of dimensional categories (see Dimensional Taxonomy below) |
| **`evidentiary_standard`** | string | Yes | Legal evidentiary standard applied (see Evidentiary Standards below) |
| **`source_url`** | string | Yes | Direct link to authoritative legal document or official press release |
| **`source_document`** | string | Yes | Human-readable source citation (e.g., "DOJ Press Release, 2011-08-01") |
| **`notes`** | string | No | Brief factual notes about the case, prosecution pattern, or special circumstances |

---

## Controlled Vocabularies

### Jurisdiction Codes

| Code | Description |
|------|-------------|
| `US_DOJ` | United States Department of Justice (federal criminal/civil) |
| `UK_SFO` | United Kingdom Serious Fraud Office (crown prosecutions) |
| `FR_PNF` | France Parquet National Financier (financial prosecutor) |
| `WB_INT` | World Bank Integrity Vice Presidency (administrative sanctions) |

**Future additions**: Country-specific codes as corpus expands (e.g., `DE_FCA` for German Federal Cartel Office, `BR_MPF` for Brazilian Federal Prosecution Service).

### Jurisdiction Types

| Type | Description |
|------|-------------|
| `federal_criminal` | Criminal prosecution with beyond-reasonable-doubt standard |
| `federal_civil` | Civil enforcement with balance-of-probabilities or clear-and-convincing standard |
| `deferred_prosecution_agreement` | DPA settlement with admission of wrongdoing |
| `convention_judiciaire` | French public interest agreement (equivalent to DPA) |
| `administrative_sanction` | World Bank/MDB debarment with more-likely-than-not standard |

### Evidentiary Standards

| Standard | Description | Typical Jurisdiction |
|----------|-------------|---------------------|
| `beyond_reasonable_doubt` | ~95% certainty, criminal prosecution standard | US DOJ (criminal), UK SFO |
| `clear_and_convincing` | ~75% certainty, civil fraud standard | US DOJ (civil) |
| `balance_of_probabilities` | ~51% certainty, preponderance of evidence | UK civil, some MDB cases |
| `more_likely_than_not` | ~51% certainty, administrative proceedings | World Bank INT |
| `intersection_of_mature_legal_systems` | Composite standard when corpus contains multiple jurisdictions | MJPIS multi-jurisdiction derivation |

---

## Dimensional Taxonomy

Cases are tagged with **dimensional categories** that represent the prosecution pattern. A case can belong to multiple dimensions if multiple patterns are present.

### Dimension 1: `markup_based`

**Definition**: Cases anchored on documented price inflation above fair market value or contract terms.

**Characteristics**:
- Markup percentage is documented and forms the evidentiary basis
- Prosecution relies on price comparison (commercial pricing, industry benchmarks, contract terms)
- Primary pattern in US DOJ False Claims Act cases

**Examples**:
- Oracle 2011: 350% markup on GSA schedule contracts
- Boeing 2006: 450% markup on spare parts
- DynCorp 2005: 75% markup on labor rates (empirical floor for US DOJ)

**Statistical Implication**: `markup_percentage` field is populated and used to derive RED/YELLOW thresholds for price-based detection.

### Dimension 2: `bribery_channel`

**Definition**: Cases anchored on documented payments through bribery intermediaries, commission structures, or kickback schemes.

**Characteristics**:
- Bribery channel payment is documented and forms the evidentiary basis
- Prosecution relies on financial flow analysis, intermediary identification, quid pro quo pattern
- Primary pattern in UK SFO and French PNF cases (FCPA, UK Bribery Act 2010, French anti-corruption law)

**Examples**:
- UK SFO case: Commission payments to shell companies controlled by procurement officials
- French PNF case: Consulting fees to intermediaries with no documented service delivery

**Statistical Implication**: `bribery_channel_amount_usd` and `bribery_channel_percentage` fields are populated and used to derive thresholds for intermediary detection patterns.

**v0.1 Note**: No bribery_channel cases in seed corpus. Dimension will be populated when UK SFO and French PNF cases are added in corpus v0.2+.

### Dimension 3: `administrative_sanctionable`

**Definition**: Cases meeting World Bank/MDB administrative sanction bar under "more likely than not" evidentiary standard.

**Characteristics**:
- Lower evidentiary bar than criminal prosecution
- Administrative debarment, contract cancellation, or repayment order
- Primary pattern in World Bank INT sanctions board cases

**Examples**:
- World Bank INT: Vendor debarred for collusive bidding based on statistical pattern analysis
- ADB: Contractor sanctioned for misrepresentation of qualifications

**Statistical Implication**: Informs YELLOW tier threshold calibration (broader net acceptable for administrative proceedings vs. criminal prosecution).

**v0.1 Note**: No administrative_sanctionable cases in seed corpus. Dimension will be populated when World Bank INT cases are added in corpus v0.2+.

---

## Adding New Cases to the Corpus

When adding cases from UK SFO, French PNF, World Bank INT, or other jurisdictions:

1. **Obtain authoritative source**: Official press release, court judgment, sanction order, or public registry entry
2. **Extract required fields**: Ensure `case_id`, `jurisdiction`, `year`, `legal_basis`, `dimensional_tags`, `evidentiary_standard`, and `source_url` are populated
3. **Infer dimensional tags**: Determine which dimension(s) the case belongs to based on the prosecution pattern:
   - If markup/overcharge is documented → add `"markup_based"`
   - If bribery intermediary payment is documented → add `"bribery_channel"`
   - If administrative sanction with lower evidentiary bar → add `"administrative_sanctionable"`
4. **Populate numerical fields**: If markup percentage or bribery amount is documented in the source, populate those fields; otherwise set to `null`
5. **Increment `corpus_version`**: Update to next semantic version (0.2, 0.3, etc.) when adding new cases
6. **Update `jurisdictions_included`**: Add new jurisdiction code if this is the first case from that jurisdiction
7. **Update `total_cases`**: Reflect new case count
8. **Re-run derivation**: The `mjpis_derivation.py` function will automatically pick up the new cases and recompute thresholds

---

## Versioning Semantics

**Corpus Version Format**: `MAJOR.MINOR`

- **MAJOR** increment: Breaking schema change (field removed, field semantics changed, dimensional taxonomy restructured)
- **MINOR** increment: Additive change (new cases added, new jurisdictions added, new fields added without breaking existing consumers)

**Current Version**: `0.1`
- Status: Seed corpus with US DOJ cases only
- Next milestone: `0.2` when UK SFO cases are added
- Production milestone: `1.0` when all four initial jurisdictions (US DOJ, UK SFO, FR PNF, WB INT) are represented

---

## Example: Adding a UK SFO Case

```json
{
  "case_id": "UK_SFO_v_RollsRoyce_2017",
  "jurisdiction": "UK_SFO",
  "jurisdiction_type": "deferred_prosecution_agreement",
  "country_code": "GB",
  "year": 2017,
  "legal_basis": "UK Bribery Act 2010",
  "case_name": "Serious Fraud Office v. Rolls-Royce plc",
  "contract_value_usd": 12000000000,
  "contract_value_local": 9600000000,
  "contract_currency": "GBP",
  "settlement_amount_usd": 671000000,
  "markup_percentage": null,
  "bribery_channel_amount_usd": 450000000,
  "bribery_channel_percentage": 3.75,
  "dimensional_tags": ["bribery_channel"],
  "evidentiary_standard": "beyond_reasonable_doubt",
  "source_url": "https://www.sfo.gov.uk/cases/rolls-royce-plc/",
  "source_document": "SFO Deferred Prosecution Agreement, 2017-01-17",
  "notes": "Payments to intermediaries in multiple countries to secure defense and energy contracts. DPA with £671M penalty. Largest UK corporate criminal settlement."
}
```

**Dimensional Classification**: This case is tagged `["bribery_channel"]` because the prosecution anchored on documented payments to intermediaries (£450M bribery channel), not on markup above fair market value.

---

## Schema Maintenance

**Steward**: Rimwaya Ouedraogo, Hugo Villalba
**Location**: `research/corpus/SCHEMA.md`
**Review Cycle**: Update SCHEMA.md when corpus schema changes (new fields added, dimensional taxonomy extended)

**Backward Compatibility Guarantee**: Existing fields will not be removed or have their semantics changed without a MAJOR version increment. New fields may be added in MINOR increments with `null` defaults for existing cases.

---

## References

- **MJPIS Derivation Function**: `code/mjpis_derivation.py`
- **Global Parameters Registry**: `code/global_parameters.py`
- **Corpus File**: `research/corpus/prosecuted_cases_global_v{VERSION}.json`
- **DOJ Source Cases**: `prosecuted_cases.json` (original US DOJ corpus, superseded by this schema)

---

**End of Schema Documentation**
