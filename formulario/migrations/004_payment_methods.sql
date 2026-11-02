CREATE TRIGGER new_contract_payment_methods BEFORE INSERT ON contracts
WHEN NEW.payment_method NOT IN ('cash','debit')
BEGIN SELECT RAISE(ABORT,'Only cash or direct debit are allowed'); END;
