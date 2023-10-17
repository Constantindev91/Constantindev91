<?php
error_reporting(-1);
$servername = "localhost"; // localhost
$username = "root"; // root
$password = "root"; // root ou rien
$dbname = "user";

$db = new PDO("mysql:host=$servername;dbname=$dbname;charset=utf8", $username, 'root');
