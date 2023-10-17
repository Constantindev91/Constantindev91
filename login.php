<?php
session_start();
require_once("bdd.php");

if ($_SERVER['REQUEST_METHOD'] == 'GET') {
    echo json_encode(["success" => false, "error" => "Ereur de connexion"]);
    die;
}

if (isset($_POST['email'], $_POST['pwd']) && !empty(trim($_POST['email'])) && !empty(trim($_POST['pwd']))) {
    $req = $db->prepare("SELECT id_user, email, pwd, admin FROM users WHERE email = ?");
    $req->execute([$_POST['email']]);

    $user = $req->fetch(PDO::FETCH_ASSOC);

    if ($user && password_verify($_POST['pwd'], $user['pwd'])) {
        $_SESSION['connected'] = true;
        $_SESSION['id'] = $user['id_user'];
        $_SESSION['admin'] = $user['admin'] == 1;

        echo json_encode(['success' => true, "admin" => $_SESSION['admin']]);
    } else echo json_encode(['success' => false, "error" => "Email ou mot de passe incorrect"]);
} else echo json_encode(['success' => false, "error" => "Veuillez remplir le formulaire de connexion"]);
