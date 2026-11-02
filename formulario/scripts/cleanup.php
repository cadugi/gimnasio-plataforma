<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/app/Service.php';ensure(PHP_SAPI==='cli','Solo CLI.');$root=dirname(__DIR__);$s=new Service($root,readConfig($root));
$s->transaction(function()use($s){$s->sql('DELETE FROM drafts WHERE expires_at<?',[instant()]);$s->sql('DELETE FROM previews WHERE expires_at<?',[instant()]);$s->sql('DELETE FROM rate_limits WHERE reset_at<?',[time()]);$s->audit('maintenance','EXPIRED_SESSIONS_PURGED','operational');});
echo "Borradores, vistas previas y contadores caducados eliminados. No se han eliminado contratos ni datos bancarios históricos.\n";
