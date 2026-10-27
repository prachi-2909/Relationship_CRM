"""Labelled commitment pairs used to MEASURE the duplicate detector (tests/test_commitment_similarity.py).

SIMILAR: two wordings of the same promise - the detector should flag them for review.
DISTINCT: two genuinely different promises that merely look alike - the detector must NEVER flag them
(a false positive here would hide a real commitment behind a "possible duplicate" prompt).
Each pair is (text_a, text_b); ownership is inferred from the wording exactly as extraction does.
"""

SIMILAR = [
    ("CSP to fix the terminal expiry issue as soon as possible.",
     "CSP commits to fixing the terminal expiry issue (no specific deadline given)."),
    ("RM to send the slab chart to the CSP.", "RM will share the slab chart with the CSP."),
    ("CSP to share the updated performance report with the RM.",
     "CSP will send the updated performance report to the RM."),
    ("CSP to complete the remaining 3 PMSBY enrollments.",
     "CSP commits to completing the remaining 3 PMSBY enrollments."),
    ("RM to visit the CSP branch.", "RM will meet the CSP at the branch."),
    ("CSP to resolve the settlement problem.", "CSP to fix the settlement issue."),
    ("RM to call the CSP back.", "RM will phone the CSP back."),
    ("CSP to submit the KYC documents.", "CSP will provide the KYC documents."),
    ("RM to update the system with the new figures.", "RM to revise the system with the updated figures."),
    ("CSP to activate the terminal by 2026-12-05.", "CSP will activate the terminal by 2026-12-05."),
    ("CSP to fix the terminal expiry issue.", "The CSP will repair the terminal expiry problem."),
    ("RM to follow up on the pending JJBY forms.", "RM will chase the pending JJBY forms."),
    ("CSP to fix the terminal.", "CSP to fix the terminal."),
]

DISTINCT = [
    ("CSP to complete the remaining 3 PMSBY enrollments.", "CSP to complete the remaining 2 PMJJBY enrollments."),
    ("RM to call the CSP on Monday.", "RM to call the CSP on Friday."),
    ("CSP to send the report by 2026-12-05.", "CSP to send the report by 2026-12-20."),
    ("CSP to open 5 new accounts.", "CSP to open 5 new APY accounts."),
    ("RM to visit the CSP branch.", "RM to visit the CSP home."),
    ("CSP to fix the terminal expiry issue.", "CSP to fix the printer paper issue."),
    ("RM to share the slab chart.", "RM to share the commission statement."),
    ("CSP to complete the account opening target.", "CSP to complete the insurance target."),
    ("CSP will not close the account.", "CSP will close the account."),
    ("CSP to call the RM.", "RM to call the CSP."),
    ("RM to send the report to the CSP.", "RM to send the invoice to the CSP."),
    ("RM to visit the CSP in January.", "RM to visit the CSP in March."),
    ("CSP to enroll 10 customers in APY.", "CSP to enroll 10 customers in PMSBY."),
    ("RM to confirm the slab target with the CSP.", "RM to review the incentive scheme with the CSP."),
    ("After terminal is fixed, CSP to complete the remaining 3 PMSBY enrollments.",
     "CSP to fix the terminal expiry issue."),
    ("RM to update the system with the new figures once received.",
     "RM commits to updating the report after receiving the CSP's updated numbers."),
    # --- adversarial: written AFTER the first version of the detector let these through ---
    ("RM to call Rakesh and discuss the terminal expiry issue.",
     "RM to call Suresh and discuss the terminal expiry issue."),          # different person
    ("CSP to reach 50 accounts this month.", "CSP to reach 50 accounts next month."),   # different period
    ("CSP to reach 50 accounts weekly.", "CSP to reach 50 accounts monthly."),          # different cadence
    ("CSP to install the terminal at branch A.", "CSP to install the terminal at branch B."),
    ("CSP to send the report to the branch manager.", "CSP to send the report to the RBO."),
    ("RM to send the report to the LHO.", "RM to send the report to the RBO."),         # different recipient
    ("RM to arrange training for the CSP staff.", "RM to arrange a loan for the CSP staff."),
]

# More re-wordings of the same promise, including capitalisation and time words that DO agree.
SIMILAR += [
    ("RM to call Rakesh about the slab.", "RM will phone Rakesh about the slab."),
    ("CSP to send the report next week.", "CSP will share the report next week."),
    ("CSP to fix the Terminal expiry issue.", "CSP to fix the terminal expiry issue."),
]
