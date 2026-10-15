-- Run in one transaction. Block writers while moving historical duplicates.
LOCK TABLE public.refunds IN ACCESS EXCLUSIVE MODE;

-- Preserve all original columns, including row IDs, and an archive timestamp.
CREATE TABLE IF NOT EXISTS public.refunds_duplicate_archive AS
SELECT refunds.*, CURRENT_TIMESTAMP AS archived_at
FROM public.refunds
WITH NO DATA;

-- Keep the earliest recorded refund for each ticket. Archive the later copies.
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY ticket_id ORDER BY created_at, id
    ) AS position
    FROM public.refunds
), moved AS (
    DELETE FROM public.refunds
    WHERE id IN (SELECT id FROM ranked WHERE position > 1)
    RETURNING *
)
INSERT INTO public.refunds_duplicate_archive (
    id, ticket_id, customer_id, refund_amount, refund_reason, analyst,
    refund_date, status, github_delivery_id, created_at, archived_at
)
SELECT id, ticket_id, customer_id, refund_amount, refund_reason, analyst,
       refund_date, status, github_delivery_id, created_at, CURRENT_TIMESTAMP
FROM moved;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.refunds'::regclass
          AND conname = 'refunds_ticket_id_unique'
    ) THEN
        ALTER TABLE public.refunds
        ADD CONSTRAINT refunds_ticket_id_unique UNIQUE (ticket_id);
    END IF;
END
$$;
