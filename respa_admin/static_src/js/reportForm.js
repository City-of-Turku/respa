export function initializeEventHandlers() {
    setDefaultDate();
    bindSelectAll();
    bindGenerateButton();
}

function setDefaultDate() {
    let date = new Date();
    $("#end-date").attr('value', date.toISOString().substr(0, 10));
    date.setMonth(date.getMonth() - 1);
    $("#begin-date").attr('value', date.toISOString().substr(0, 10));
}

function buildUrl(resources, start, end, page_size = 50000, format = 'xlsx') {
    return `${window.location.origin}/v1/reservation/?format=${format}&resource=${resources.join()}&start=${start}&end=${end}&page_size=${page_size}&state=confirmed`;
}


let selectState = false;
let lang = 'en';

function bindSelectAll() {
    let selectBtn = $("#select-all-btn");
    lang = $(selectBtn).attr('lang');
    $(selectBtn).on('click', () => {
        selectState = !selectState;
        $(".resource-card input").each((i, resource) => {
            $(resource).prop('checked', selectState);
        });
        if (selectState) {
            switch(lang) {
                case 'fi':
                    $(selectBtn).text('Poista valinnat');
                    return;
                case 'sv':
                    $(selectBtn).text('Avmarkera alla');
                    return;
                default:
                    $(selectBtn).text('Deselect all');
                    return;
            }
        } else {
            switch(lang) {
                case 'fi':
                    $(selectBtn).text('Valitse kaikki');
                    return;
                case 'sv':
                    $(selectBtn).text('Välj alla');
                    return;
                default:
                    $(selectBtn).text('Select all');
                    return;
            }
        }
    });
}

function getDateError() {
    switch(lang) {
        case 'fi':
            return 'Alkupäivä ei voi olla suurempi kuin loppupäivä.';
        case 'sv':
            return 'Startdatum kan inte vara större än slutdatum.';
        default:
            return 'Start date cannot be greater than end date.';
    }
}

function bindGenerateButton() {
    let btn = $("#generate-btn");
    $(btn).on('click', () => {
        let resources = [];
        $(".resource-card input:checked").each((i, resource) => {
            resources.push($(resource).attr('id'));
        });

        let begin = $("#begin-date").val();
        let end = $("#end-date").val();

        if (new Date(begin) > new Date(end)) {
            alert(getDateError());
            return;
        }

        var http = new XMLHttpRequest();
        http.responseType = 'blob';
        http.onreadystatechange = () => {
            if (http.status === 200 && http.readyState === 4) {
                var url = window.URL.createObjectURL(http.response);
                let dl = document.createElement('a');
                dl.href = url;
                dl.download = 'report.xlsx';
                dl.click();
                $("body").css("cursor", "default");
            }
        }
        http.open('GET', buildUrl(resources, begin, end));
        http.send();
        $("body").css("cursor", "progress");
    });

    setInterval(() => {
        if ($(".resource-card input:checked").length > 0) {
            $(btn).prop('disabled', false);
        } else {
            $(btn).prop('disabled', true);
        }
    }, 200);
}