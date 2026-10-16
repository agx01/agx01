"""Synthetic payloads shaped like the real sources.

**These are hand-built, not captured.** `sec.gov` is denied by the authoring container's
egress policy (../../docs/12-environment-notes.md), so the shapes come from prior
knowledge of EDGAR rather than from a fetched sample. They encode the structural traps
the parsers must survive — parallel arrays of unequal length, a malformed accession, two
vintages of one fact, a 10b5-1 plan disclosed only in a footnote — and they are **not**
evidence that the real payloads look like this. Validate against a live response from
your workstation before trusting the parsers (../../docs/references.md, S1–S5).
"""

from __future__ import annotations

from typing import Any

APPLE_CIK = "0000320193"

#: ``filings.recent`` is parallel arrays. ``reportDate`` is deliberately SHORTER than
#: ``accessionNumber`` here: a naive ``zip`` would silently drop the last rows.
SUBMISSIONS: dict[str, Any] = {
    "cik": "320193",
    "entityName": "Apple Inc.",
    "name": "Apple Inc.",
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "formerNames": [
        {"name": "APPLE COMPUTER INC", "from": "1994-01-26", "to": "2007-01-10"}
    ],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-24-000123",
                "0000320193-24-000110",
                "0000320193-24-000101",
                "0001214156-24-000044",
                "not-an-accession",
                "0000320193-23-000064",
            ],
            "form": ["10-K", "8-K", "10-Q", "4", "10-Q", "10-K/A"],
            "filingDate": [
                "2024-11-01",
                "2024-10-31",
                "2024-08-02",
                "2024-10-28",
                "2024-05-03",
                "2023-11-03",
            ],
            "reportDate": ["2024-09-28", "2024-10-31", "2024-06-29"],
            "primaryDocument": [
                "aapl-20240928.htm",
                "aapl-8k_20241031.htm",
                "aapl-20240629.htm",
                "xslF345X05/wf-form4_172.xml",
                "aapl-20240330.htm",
                "aapl-20230930.htm",
            ],
            "items": ["", "2.02,9.01", "", "", "", ""],
        },
        "files": [],
    },
}

#: Revenues has two vintages of FY2024 (original and a restating filing) plus FY2023,
#: and Assets is an instant fact.
COMPANY_FACTS: dict[str, Any] = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 391035000000,
                            "accn": "0000320193-24-000123",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "frame": "CY2024",
                        },
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 391036000000,
                            "accn": "0000320193-25-000010",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                        },
                        {
                            "start": "2022-09-25",
                            "end": "2023-09-30",
                            "val": 383285000000,
                            "accn": "0000320193-23-000106",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                        },
                        {"start": "2023-10-01", "end": "2024-09-28", "val": None},
                    ]
                },
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "USD": [
                        {
                            "end": "2024-09-28",
                            "val": 364980000000,
                            "accn": "0000320193-24-000123",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                        }
                    ]
                },
            },
        },
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}},
    },
}

#: A Form 4 with two non-derivative lines: an open-market sale whose 10b5-1 plan is
#: disclosed only in a footnote, and an indirect-ownership grant.
FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0508</schemaVersion>
  <documentType>4</documentType>
  <periodOfReport>2024-10-28</periodOfReport>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214156</rptOwnerCik>
      <rptOwnerName>COOK TIMOTHY D</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2024-10-28</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>223986</value></transactionShares>
        <transactionPricePerShare><value>225.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>3280222</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
      </ownershipNature>
      <transactionAmountsFootnote id="F1"/>
      <footnoteId id="F1"/>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Restricted Stock Unit</value></securityTitle>
      <transactionDate><value>2024-10-01</value></transactionDate>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>3780222</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <footnotes>
    <footnote id="F1">This sale was made pursuant to a Rule 10b5-1 trading plan adopted
      on April 2, 2024.</footnote>
  </footnotes>
</ownershipDocument>
"""

#: Same shape, but with the modern explicit plan element instead of footnote prose.
FORM4_XML_EXPLICIT_PLAN = b"""<?xml version="1.0"?>
<ownershipDocument>
  <periodOfReport>2024-11-04</periodOfReport>
  <aff10b5One>true</aff10b5One>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001051401</rptOwnerCik>
      <rptOwnerName>WILLIAMS JEFFREY E</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>1</isOfficer>
      <officerTitle>COO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2024-11-04</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>222.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

EODHD_SEARCH: list[dict[str, Any]] = [
    {
        "Code": "AAPL",
        "Exchange": "US",
        "Name": "Apple Inc",
        "Type": "Common Stock",
        "Country": "USA",
        "Currency": "USD",
        "ISIN": "US0378331005",
    },
    {
        "Code": "AAPL",
        "Exchange": "MX",
        "Name": "Apple Inc",
        "Type": "Common Stock",
        "Currency": "MXN",
        "ISIN": "NOT-AN-ISIN",
    },
    {"Name": "row with no code"},
]

EODHD_FUNDAMENTALS: dict[str, Any] = {
    "General": {
        "Code": "AAPL",
        "Name": "Apple Inc",
        "Exchange": "NASDAQ",
        "CurrencyCode": "USD",
        "CountryISO": "US",
        "CIK": "320193",
        "ISIN": "US0378331005",
        "Sector": "Technology",
        "Industry": "Consumer Electronics",
        "WebURL": "https://www.apple.com",
        "FullTimeEmployees": 164000,
        "FiscalYearEnd": "September",
    },
    "Highlights": {"MarketCapitalization": 3_400_000_000_000},
}

EODHD_FUNDAMENTALS_NO_CIK: dict[str, Any] = {
    "General": {
        "Code": "ASML",
        "Name": "ASML Holding NV",
        "LEI": "724500Y6DUVHQD6OXN27",
        "CountryISO": "NL",
        "WebURL": "https://www.asml.com",
    }
}
