$('#submit').click((event) => {
    event.preventDefault();

    $.ajax({
        url: 'login.php',
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
                window.location.replace('../home/home.html') 
            } else alert(res.error);
        }
    });
});