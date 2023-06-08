import { initializeEventHandlers } from './notificationsForm';


function start() {
    initializeEventHandlers();
}

window.addEventListener('load', start, false);