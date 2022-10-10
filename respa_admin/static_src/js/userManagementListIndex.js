import { Paginate } from './utils';


let paginators = [];


function start() {
    handlePagination();
}





function handlePagination() {
    $("div[data-paginate=true]").each((i, div) => {
      paginators.push(new Paginate(div));
    });
  }


window.addEventListener('load', start, false);