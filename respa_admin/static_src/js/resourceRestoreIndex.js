import { initializeEventHandlers } from './resourceRestore';


function start() {
    initializeEventHandlers();
}

window.addEventListener('load', start, false);