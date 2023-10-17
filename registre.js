$('#submit').click((event) => {
    event.preventDefault();

    $.ajax({
        url: 'registre.php',
        type: 'POST',
        dataType: 'json',
        data: {
            firstname: $('#firstname').val(),
            lastname: $('#lastname').val(),
            birthdate: $('#birthdate').val(),
            email: $('#email').val(),
            pwd: $('#pwd').val()
        },
        success: (res) => {
            res.success ? window.location.replace('Connectez-vous.html') : alert(res.error);
        }
    });
});