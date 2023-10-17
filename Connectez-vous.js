$('#submit').click((event) => {
    event.preventDefault();

    $.ajax({
        url: 'Connectez-vous.php',
        type: 'POST',
        dataType: 'json',
        data: {
            email: $('#email').val(),
            pwd: $('#pwd').val()
        },
        success: (res) => {
            if (res.success) {
                localStorage.setItem('connected', true);
                localStorage.setItem('admin', res.admin);
                window.location.replace('registre.html') 
            } else alert(res.error);
        }
    });
});