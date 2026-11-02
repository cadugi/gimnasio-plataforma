<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=UTF-8');
header('X-Content-Type-Options: nosniff');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['success'=>false,'error'=>'METHOD_NOT_ALLOWED']); exit;
}

$targetDir = __DIR__ . '/img';
if (!is_dir($targetDir)) { http_response_code(500); echo json_encode(['success'=>false,'error'=>'IMG_DIR_MISSING']); exit; }

if (!isset($_FILES['archivo']) || !is_uploaded_file($_FILES['archivo']['tmp_name'])) {
    http_response_code(400); echo json_encode(['success'=>false,'error'=>'NO_FILE']); exit;
}

$maxSize = 15 * 1024 * 1024; // 15MB
if ($_FILES['archivo']['size'] > $maxSize) { http_response_code(400); echo json_encode(['success'=>false,'error'=>'FILE_TOO_LARGE','max'=>$maxSize]); exit; }

$origName = $_FILES['archivo']['name'];
$tmpPath  = $_FILES['archivo']['tmp_name'];
if (($_FILES['archivo']['error'] ?? UPLOAD_ERR_OK) !== UPLOAD_ERR_OK) { http_response_code(400); echo json_encode(['success'=>false,'error'=>'UPLOAD_FAILED']); exit; }

$ext = strtolower(pathinfo($origName, PATHINFO_EXTENSION));
$allowed = ['jpg','jpeg','png','webp'];
if (!in_array($ext, $allowed, true)) {
    http_response_code(400);
    echo json_encode(['success'=>false,'error'=>'ONLY_IMAGES','allowed'=>$allowed]);
    exit;
}
// El contenido manda, no el nombre: tiene que ser realmente una imagen JPEG, PNG o WebP, coherente con la extensión y de tamaño razonable.
$info = @getimagesize($tmpPath);
$types = [IMAGETYPE_JPEG => ['jpg','jpeg'], IMAGETYPE_PNG => ['png'], IMAGETYPE_WEBP => ['webp']];
if (!$info || !isset($types[$info[2]])) { http_response_code(400); echo json_encode(['success'=>false,'error'=>'NOT_AN_IMAGE']); exit; }
if (!in_array($ext, $types[$info[2]], true)) { http_response_code(400); echo json_encode(['success'=>false,'error'=>'EXTENSION_MISMATCH']); exit; }
if ($info[0] < 200 || $info[1] < 200 || $info[0] > 8000 || $info[1] > 8000 || $info[0] * $info[1] > 40000000) {
    http_response_code(400); echo json_encode(['success'=>false,'error'=>'IMAGE_DIMENSIONS','min'=>200,'max'=>8000]); exit;
}
// Se prepara el archivo nuevo ANTES de tocar el actual: si algo falla, la imagen anterior sigue intacta.
$staged = $targetDir . '/horario.nuevo.' . bin2hex(random_bytes(6)) . '.tmp';
if (!@move_uploaded_file($tmpPath, $staged) && !@copy($tmpPath, $staged)) {
    http_response_code(500); echo json_encode(['success'=>false,'error'=>'MOVE_FAIL']); exit;
}
@chmod($staged, 0644);

// Rotar activos anteriores si existe horario.jpg
$finalImagePath = $targetDir . '/horario.jpg';
$candidate = null;
for ($i=5;$i>=1;$i--) {
    $prev = $targetDir . '/horario.' . $i . '.jpg';
    if (is_file($prev)) {
        $next = $targetDir . '/horario.' . ($i+1) . '.jpg';
        @rename($prev, $next);
    }
}
if (is_file($finalImagePath)) {
    $candidate = $targetDir . '/horario.1.jpg';
    @rename($finalImagePath, $candidate);
}

// Activar la imagen nueva (rename atómico); si falla, se restaura la anterior
if (!@rename($staged, $finalImagePath)) {
    @unlink($staged);
    if (isset($candidate) && is_file($candidate)) @rename($candidate, $finalImagePath);
    http_response_code(500); echo json_encode(['success'=>false,'error'=>'MOVE_FAIL']); exit;
}

echo json_encode([
    'success'=>true,
    'active'=>'img/horario.jpg',
    'archived_previous'=> isset($candidate) ? basename($candidate) : null
], JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
