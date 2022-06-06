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
          let apiUrl = `${window.location.origin}/v1/o365/start_connect_resource_to_calendar/`;
          let resource_id = $(form).attr('id');
          $.ajax({
            'type': 'GET',
            'url': `${apiUrl}?resource_id=${resource_id}&return_to=${window.location.href}/ra/outlook/`,
            'beforeSend': (xhr) => {
              xhr.setRequestHeader("X-CSRFToken", $(form).serialize().split('=')[1]);
            },
            'success': (response) => {
              window.location.href = response.redirect_link;
            },
          });
        })
      })
  });
}