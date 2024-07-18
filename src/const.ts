import { existsSync, mkdirSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";


const realScriptPath = realpathSync(process.argv[1]);
export const PROJECT_ROOT = join(dirname(realScriptPath), '..');

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


