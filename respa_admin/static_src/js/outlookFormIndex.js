import { initializeEventHandlers } from './outlookForm';


function start() {
    initializeEventHandlers();
}

window.addEventListener('load', start, false);