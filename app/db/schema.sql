-- One row represents one validated completed refund.
CREATE TABLE IF NOT EXISTS public.refunds (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id BIGINT NOT NULL CONSTRAINT refunds_ticket_id_unique UNIQUE CHECK (ticket_id > 0),
    customer_id TEXT NOT NULL CHECK (length(trim(customer_id)) > 0),
    refund_amount NUMERIC(12, 2) NOT NULL CHECK (
        refund_amount > 0 AND refund_amount <> 'NaN'::numeric
    ),
    refund_reason TEXT NOT NULL CHECK (length(trim(refund_reason)) > 0),
    analyst TEXT NOT NULL CHECK (length(trim(analyst)) > 0),
    refund_date TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status = 'completed'),
    github_delivery_id TEXT NOT NULL UNIQUE CHECK (length(trim(github_delivery_id)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
