CREATE UNIQUE INDEX one_active_mandate_per_contract ON mandates(contract_id) WHERE state='ACTIVE';
CREATE UNIQUE INDEX one_pending_bank_change ON mandates(replaces_id) WHERE state='PENDING_HOLDER' AND replaces_id IS NOT NULL;
CREATE INDEX contract_versions ON contracts(previous_id,center_accepted_at);
CREATE TRIGGER signed_identity_immutable BEFORE UPDATE OF id,reference,created_at,is_demo,previous_id ON contracts BEGIN SELECT RAISE(ABORT,'immutable signed identity'); END;
CREATE TRIGGER mandate_bank_immutable BEFORE UPDATE OF reference,member_id,contract_id,bank_enc,last_four,holder_same,replaces_id ON mandates BEGIN SELECT RAISE(ABORT,'new mandate required for bank changes'); END;
