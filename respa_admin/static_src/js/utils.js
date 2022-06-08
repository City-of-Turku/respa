export function alertPopup(message, type = 'success') {
    let popup = $("div[id=popup-notification]");
    let popupSpan = $(popup).find('span[id=popup-message]');

    switch(type) {
        case 'success':
            $(popup).addClass('success');
        break;
        case 'error':
            $(popup).addClass('error');
        break;
        default:
        break
    }

    $(popupSpan).text(message);
    $(popup).fadeIn('slow').css('display', 'flex');

    setTimeout(() => {
        $(popup).fadeOut('slow');
        setTimeout(() => {
        $(popupSpan).text('');
        }, 500);
    }, 5000);
}
  