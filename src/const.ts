import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import {packageDirectorySync} from 'pkg-dir';

export const PROJECT_ROOT = packageDirectorySync()!;

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


