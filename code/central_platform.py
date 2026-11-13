"""Narrow FTS contract-details projection; raw notice bodies never enter storage.

Not a legal classifier. A signature date remains a signature date. The fixed
publisher marker selects contract-details documents, not every award-tagged
release. Unknown fields and all personal/contact/free-text fields are dropped.
"""
from watch_journal import admit
from watch_projection import FieldRefusal, select_fields

VERSION = 'central-platform-contract-details.v1'
FIELDS = {
    'ocid': 'identifier', 'id': 'identifier', 'date': 'timestamp',
    'tender': {'legalBasis': {'scheme': 'scheme', 'id': 'identifier'}},
    'contracts': [{'id': 'identifier', 'awardID': 'identifier',
                   'dateSigned': 'timestamp', 'aboveThreshold': 'boolean',
                   'documents': [{'id': 'identifier', 'datePublished': 'timestamp'}]}],
}
MARKER = 'Contract details notice on Find a Tender'


def project_record(row, source_version=None):
    if not isinstance(row, dict):
        raise FieldRefusal('/', 'invalid_object')
    selected = dict(row)
    raw_contracts = row.get('contracts')
    if isinstance(raw_contracts, list):
        contracts = []
        for ci, contract in enumerate(raw_contracts):
            if not isinstance(contract, dict):
                raise FieldRefusal(f'/contracts/{ci}', 'invalid_object')
            safe = dict(contract)
            docs = contract.get('documents')
            if isinstance(docs, list):
                # Empty slots retain the original array index and source locator.
                safe['documents'] = [d if isinstance(d, dict) and
                    d.get('description') == MARKER and d.get('documentType') == 'contractNotice'
                    else {} for d in docs]
            contracts.append(safe)
        selected['contracts'] = contracts
    mapped, gaps = [], {}
    projected = select_fields(selected, FIELDS, '', mapped, gaps)
    for key in ('ocid', 'id'):
        if not projected.get(key):
            raise FieldRefusal('/' + key, 'missing_release_identity')
    coverage = {'adapter_version': VERSION, 'publisher_version': source_version,
                'mapped_fields': sorted(mapped), 'gaps': dict(sorted(gaps.items())),
                'excluded_by_policy': ['names', 'contacts', 'addresses', 'free_text', 'attachments', 'party_records'],
                'population_complete': None,
                'limits': 'Field presence does not establish entry into contract, legal scope, initial publication or absence of alternative publication.'}
    admit(projected)
    admit(coverage)
    return projected, coverage
