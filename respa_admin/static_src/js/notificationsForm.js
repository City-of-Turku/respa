import { alertPopup, Paginate, getErrorMessage, ajaxRequest } from './utils';


let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);
    bindTogglePreviewModal();
    bindLangTabs();
}


let previewState = false;
let selectedTab = 'fi';


function bindLangTabs() {
    const tabButtons = $("a[tab-button]");
    const langContainers = $("div[lang-container]");
    $(tabButtons).each((_, btn) => {
        $(btn).on('click', (e) => {
            e.preventDefault();
            if (previewState) { $("#close-modal-btn").click(); }
            $(tabButtons).removeClass('active');
            $(langContainers).hide();
            const lang = $(btn).data('value');
            selectedTab = lang;
            $(langContainers).each((_, container) => {
                if ($(container).data('value') === lang) {
                    $(container).show();
                    $(btn).addClass('active');
                }
            });
        })
    })
}


function bindTogglePreviewModal() {
    let previewButton = $("button[id^=preview-modal-btn-]");
    $(previewButton).on('click', (_) => {
        let previewModal = $(`div[id=previewModal-${selectedTab}`);
        if (previewState) { $("#close-modal-btn").click(); return; }

        let html = $(`textarea[id=id_html_body-${selectedTab}`).val();
        $(previewModal).css({ 
            'top': `${($(window).scrollTop() + 10)}px`,
            'left': '60%',
            'display': 'block',
            'position': 'absolute',
        });
        $(`<div id="inject-preview-html" 
                style="display: flex; flex-direction: row-reverse; justify-content: flex-end;">
                <div 
                    style="width: 100%; height: 25px; style="border: 2px solid black; cursor: pointer;">
                    <button type"button" id="close-modal-btn">&times;</button>
                </div>
                ${html}
            </div>`).appendTo($(previewModal));
        $("#close-modal-btn").on('click', (e) => {
            $("#inject-preview-html").remove();
            previewState = false;
            $(previewButton).text('Preview');
        });
        previewState = true;
        $(previewButton).text('Close');
    });
}