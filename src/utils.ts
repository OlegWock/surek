import { log } from "@src/logger";

export const exit = (message: string = '', code = 1): never => {
    if (message) {
        log.error(message);
    }
    process.exit(code);
}