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

        this.prevPageButton = $(`
            <a href="javascript://" id=\"prev_page_${this.id}\" class="btn"><span class="glyphicon glyphicon-chevron-left"></span></a>
            `).appendTo(this._pageContainer)
            .on('click', (e) => {
                e.preventDefault();
                $(this.current()).hide();
                $(this.previous()).show();
            });

        this.pageTrackSpan = $(`
            <span id="paginator-page" class="no-select align-center btn"></span>
            `).appendTo(this._pageContainer);

        this.nextPageButton = $(`
            <a href="javascript://" id=\"next_page_${this.id}\" class="btn"><span class="glyphicon glyphicon-chevron-right"></span></a>
            `).appendTo(this._pageContainer)
            .on('click', (e) => {
                e.preventDefault();
                $(this.current()).hide();
                $(this.next()).show();
            });
        
        this.prevPageButton.hide();
        this.nextPageButton.hide();


        this.reset();
    }

    update() {
        if (this.totalPages > 1) $(this.nextPageButton).show();
        if (!this.hasNextPage()) $(this.nextPageButton).hide();
        if (this.page > 0) {
            $(this.prevPageButton).show();
        } else $(this.prevPageButton).hide();

        this.setPageText(`${
            {'fi': 'Sivu', 'en': 'Page', 'sv': 'Page'}[$('html').attr('lang')]
        }: ${this.page + 1}`);
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