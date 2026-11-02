<?php
declare(strict_types=1);
require_once __DIR__.'/Core.php';require_once __DIR__.'/AccessPassword.php';require_once __DIR__.'/Validation.php';require_once __DIR__.'/Proration.php';require_once __DIR__.'/PaperReference.php';require_once __DIR__.'/Pdf.php';require_once __DIR__.'/Review.php';require_once __DIR__.'/BankFile.php';require_once __DIR__.'/Contracts.php';require_once __DIR__.'/InnuxAdapter.php';require_once __DIR__.'/Billing.php';require_once __DIR__.'/Admin.php';
require_once __DIR__.'/Mandates.php';
require_once __DIR__.'/Photos.php';
require_once __DIR__.'/InnuxNumber.php';
require_once __DIR__.'/Tablets.php';
require_once __DIR__.'/InnuxConnector.php';
require_once __DIR__.'/Retirements.php';
require_once __DIR__.'/Mail.php';
require_once __DIR__.'/MemberExport.php';
require_once __DIR__.'/Withdrawals.php';
require_once __DIR__.'/History.php';require_once __DIR__.'/Sso.php';
require_once __DIR__.'/Members.php';
final class Service extends Runtime {use MemberOperations;use MailOperations;use MemberExportOperations;use WithdrawalOperations;use HistoryOperations;use SsoOperations;use RetirementOperations;use InnuxConnectorOperations;use TabletOperations;use InnuxNumberOperations;use ContractOperations;use BillingOperations;use AdminOperations;use MandateOperations;use PhotoOperations;}
