import { log } from "@src/utils/logger";

export const exit = (message: string = '', code = 1): never => {
    if (message) {
        log.error(message);
    }
    process.exit(code);
}