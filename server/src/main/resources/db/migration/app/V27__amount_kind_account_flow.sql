-- ADR-0007: extend the closed amount-kind set. Do not edit V14.
ALTER TABLE app.case_amount DROP CONSTRAINT ck_case_amount_kind;
ALTER TABLE app.case_amount ADD CONSTRAINT ck_case_amount_kind CHECK (kind IN (
    'payment_settlement_amount', 'illegal_gain', 'crime_amount',
    'business_revenue', 'recovery', 'fine',
    'account_total_flow', 'provided_funds_amount'
));
