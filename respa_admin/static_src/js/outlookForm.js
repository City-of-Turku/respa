export function initializeEventHandlers() {
    bindRemoveLinkButton();
    bindAddLinkButton();
}


function bindRemoveLinkButton() {
    $("form[action=remove]").each((i, form) => {
      $(form).find('.card-body button').each((i, button) => {
          $(button).on('click', (e) => {
            e.preventDefault();
            let apiUrl = `${window.location.origin}/ra/outlook/`;
            $.ajax({
              'type': 'DELETE',
              'url': apiUrl,
              'beforeSend': (xhr) => {
                xhr.setRequestHeader("X-CSRFToken", $(form).serialize().split('=')[1]);
              },
              'data': {
                'outlook_id': $(form).attr('id')
              },
              'success': (response) => {
                alert(response.message);
                location.reload();
              },
              'error': (response) => {
                let error = $.parseJSON(response.responseText);
                alert(error.message);
              },
            });
          })
        })
    });
}

function bindAddLinkButton() {
  $("form[action=add]").each((i, form) => {
    $(form).find('.card-body button').each((i, button) => {
        $(button).on('click', (e) => {
          e.preventDefault();
          let apiUrl = `${window.location.origin}/ra/outlook/`;
          let resource_id = $(form).attr('id');
          $.ajax({
            'type': 'POST',
            'url': apiUrl,
            'beforeSend': (xhr) => {
              xhr.setRequestHeader("X-CSRFToken", $(form).serialize().split('=')[1]);
            },
            'data': {
              'resource_id': resource_id,
              'return_to': apiUrl
            },
            'success': (response) => {
              window.location.href = response.redirect_link;
            },
            'error': (response) => {
              alert('Something went wrong');
            }
          });
        })
      })
  });
}