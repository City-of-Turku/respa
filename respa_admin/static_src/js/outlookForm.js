import { alertPopup } from './utils';


export function initializeEventHandlers() {
    bindRemoveLinkButton();
    bindAddLinkButton();
}


function getErrorMessage(response) {
  let error = $.parseJSON(response.responseText);
  return error.message;
}


function bindRemoveLinkButton() {
    $("form[action=remove]").each((i, form) => {
      $(form).find('.card-body button').each((i, button) => {
          $(button).on('click', (e) => {
            e.preventDefault();
            let apiUrl = `${window.location.origin}/ra/outlook`;
            $.ajax({
              'type': 'DELETE',
              'url': `${apiUrl}/delete/`,
              'beforeSend': (xhr) => {
                xhr.setRequestHeader("X-CSRFToken", $(form).serialize().split('=')[1]);
              },
              'data': {
                'outlook_id': $(form).attr('id')
              },
              'success': (response) => {
                alertPopup('Outlook link removed');
                setTimeout(() => { location.reload(); }, 1000);
              },
              'error': (response) => {
                alertPopup(getErrorMessage(response), 'error');
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
          let apiUrl = `${window.location.origin}/ra/outlook`;
          let resource_id = $(form).attr('id');
          $.ajax({
            'type': 'POST',
            'url': `${apiUrl}/create/`,
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
              alertPopup(getErrorMessage(response), 'error');
            }
          });
        })
      })
  });
}