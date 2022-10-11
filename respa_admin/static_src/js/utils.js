export function alertPopup(message, type = 'success', timeout = 5000) {
    let popup = $("div[id=popup-notification]");
    let popupSpan = $(popup).find('span[id=popup-message]');
    $(popupSpan).addClass('no-select');

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

    let moveWithScroll = () => {
        $(popup).css({ 'top': `${($(window).scrollTop())}px` });
    }

    $(window).on('scroll', moveWithScroll);

    $(popupSpan).text(message);
    $(popup).css({
        'top': `${($(window).scrollTop())}px`,
        'display': 'flex',
    }).fadeIn('slow');

    setTimeout(() => {
        $(popup).fadeOut('slow');
        setTimeout(() => { $(popupSpan).text(''); }, 500);
        $(window).off('scroll', moveWithScroll);
    }, timeout);
}



export class Paginate {
    constructor(main) {
        this.main = $(main);
        this.id = this.main.data('paginator-id');
        this.perPage = this.main.data('paginator-per-page');
        this.totalPages = 0;

        this.items = this.main
            .find('[data-paginator-item=true]')
            .toArray();

        this._pageContainer = this.main
            .parent()
            .find(`div[id=paginator-page-container]`)
            .filter((_, e) => $(e).data('paginator-id') === this.id);

        this.reset();
    }

    updatePageSelections() {
        $(this._pageContainer)
        .find(`a[id^=${this.id}_page_]`)
        .remove();
        for(let i=0;i<this.totalPages;i++) {
            $(`<a href="javascript://" id="${this.id}_page_${i+1}" class="btn ${i === 0 ? "btn-selected" : ""} input-label" data-page="${i}">${i+1}</a>`)
            .css({ 'flex': '1 0 10%', 'width': '54px', 'max-width': '54px' })
            .appendTo(this._pageContainer)
            .on('click', (e) => {
                e.preventDefault();
                let page = $(e.target).data('page');
                this.page = page;
                this.hide(this.items);
                this.show(this.current());
            })
        }
    }


    update() {
        this.updatePageSelections();
        $(this._pageContainer)
        .find(`a[id^=${this.id}_page_]`)
        .removeClass('btn-selected')
        .each((_, val) => {
            let page = $(val).data('page');
            if (page === this.page) $(val).addClass('btn-selected');
        });
    }
    setPageText(text) { $(this.pageTrackSpan).text(text); }

    hasNextPage() {
        return this.paginatedItems[this.page + 1] !== undefined && this.paginatedItems[this.page + 1].length > 0;
    }

    next() {
        this.page++;
        return this.current();
    }

    previous() {
        this.page--;
        return this.current();
    }

    current() {
        if (!this.paginatedItems[this.page]) {
            if (this.page >= this.totalPages) {
                this.page = this.totalPages - 1;
            } else this.page = 0;
        }
        this.update();
        return this.paginatedItems[this.page];
    }

    show(items = []) { $(items).show(); }
    hide(items = []) { $(items).hide(); }

    getPaginatedItems(items = []) {
        return (items.length > 0 ? items : this.items).reduce((arr, val, i) => {
            let idx = Math.floor(i / this.perPage);
            let page = arr[idx] || (arr[idx] = []);
            page.push(val);
            return arr;
        }, []);
    }

    reset(page = 0) {
        page = page < 0 ? 0 : page;
        this.paginatedItems = this.getPaginatedItems();
        this.hide(this.items);
        this.totalPages = this.paginatedItems.length;
        this.page = page > this.totalPages ? this.totalPages - 1 : page;

        this.show(this.current());
    }

    filter(string, page = 0) {
        this.paginatedItems = this.getPaginatedItems(
            this.items.filter((val) => {
                let labelString = $(val).find('label').text().toLowerCase();
                if (labelString.indexOf(string.toLowerCase()) > -1) 
                    return val;
            })
        );
        this.hide(this.items);
        this.totalPages = this.paginatedItems.length;
        this.page = page > this.totalPages ? this.totalPages - 1 : page;
        this.show(this.current());
    }
}