import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

export const PROJECT_ROOT = dirname(process.argv[1]);

export const getDataDir = () => {
    const dataDir = join(process.cwd(), 'surek-data');
    if (!existsSync(dataDir)) {
        mkdirSync(dataDir, { recursive: true });
    }
    return dataDir;
};
export const SYSTEM_DIR = join(PROJECT_ROOT, 'system');
export const SYSTEM_SERVICES_CONFIG = join(SYSTEM_DIR, 'surek.stack.yml');

export const SUREK_NETWORK = 'surek';

export const DEFAULT_SUREK_LABELS = {
    'surek.managed': 'true',
};

export const IS_DEV = process.env.NODE_ENV === 'development';


