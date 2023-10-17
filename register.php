<?php
session_start();
require_once("bdd.php");
error_reporting(-1);


if ($_SERVER['REQUEST_METHOD'] == 'GET') {
    echo json_encode(['success' =>  false, "error" => "Erreur d'inscription"]);
    die;
}

if (
    isset($_POST['firstname'], $_POST['lastname'], $_POST['birthdate'], $_POST['email'], $_POST['pwd']) &&
    !empty(trim($_POST['firstname'])) &&
    !empty(trim($_POST['lastname'])) &&
    !empty(trim($_POST['birthdate'])) &&
    !empty(trim($_POST['email'])) &&
    !empty(trim($_POST['pwd']))
) {
   
    $hash = password_hash($_POST['pwd'], PASSWORD_DEFAULT);

    $req = $db->prepare("INSERT INTO users(firstname, lastname, birthdate, email, pwd) VALUES (?, ?, ?, ?, ?)");
    $req->execute([$_POST['firstname'], $_POST['lastname'], $_POST['birthdate'], $_POST['email'], $hash]);

    echo json_encode(['success' => true]);
} else echo json_encode(['success' => false, "error" => "Veuillez remplir tout le formulaire d'inscription"]);
