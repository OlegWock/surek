import { z, ZodEffects } from "zod";
import { fromError } from 'zod-validation-error';
import yaml from 'js-yaml';
import camelcaseKeys from 'camelcase-keys';
import { CamelCasedPropertiesDeep } from 'type-fest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { exit } from "@src/utils";
import { log } from "@src/logger";
import { PROJECT_ROOT } from "@src/const";

export const zodToCamelCase = <T extends z.ZodTypeAny>(zod: T): ZodEffects<z.ZodTypeAny, CamelCasedPropertiesDeep<T['_output']>> => zod.transform((val) => camelcaseKeys(val, { deep: true }) as CamelCasedPropertiesDeep<T>)

const configSchema = zodToCamelCase(z.object({
    root_domain: z.string(),
    default_auth: z.string().refine((val) => typeof val !== 'string' || val.split(':').length === 2, {
        message: "Auth string should be in <user>:<password> format",
    }),
}));

export type SurekConfig = z.infer<typeof configSchema>;

export const loadConfig = (): SurekConfig => {
    const possibleFilenames = ["surek.yml", "surek.yaml"];
    const path = possibleFilenames.find(name => existsSync(join(PROJECT_ROOT, name)));
    if (!path) {
        log.error(`Config file not found. Make sure you have file surek.yml around`);
        return exit();
    }
    const parsed = yaml.load(readFileSync(path, { encoding: 'utf-8' }));
    try {
        const validated = configSchema.parse(parsed);
        return validated;
    } catch (err) {
        const validationError = fromError(err);
        log.error('Error while loading config');
        log.error(validationError.toString());
        return exit();
    }
};


const stackConfigSchema = zodToCamelCase(z.object({
    name: z.string(),
    source: z.discriminatedUnion("type", [
        z.object({ type: z.literal("local") }),
        z.object({ type: z.literal("github"), slug: z.string() }),
    ]),
    compose_file_path: z.string().default(`./docker-compose.yml`),
    public: z.array(
        z.object({
            domain: z.string(),
            target: z.string(),
            auth: z.string().optional().refine((val) => typeof val !== 'string' || val === '<default_auth>' || val.split(':').length === 2, {
                message: "Auth string should be either in <user>:<password> format or '<default_auth>' literal",
            }),
        })
    ).optional().transform(v => v ?? []),
    ignore_logs_from: z.array(z.string()).optional().transform(v => v ?? []),
    backup: z.object({
        exclude_volumes: z.array(z.string()).optional().transform(v => v ?? []),
    }).optional().default({}),
}));

export type StackConfig = z.infer<typeof stackConfigSchema>;

export const loadStackConfig = (path: string) => {
    const parsed = yaml.load(readFileSync(path, { encoding: 'utf-8' }));
    try {
        const validated = stackConfigSchema.parse(parsed);
        return validated;
    } catch (err) {
        const validationError = fromError(err);
        log.error(`Error while loading stack config at ${path}`);
        log.error(validationError.toString());
        return exit();
    }
}