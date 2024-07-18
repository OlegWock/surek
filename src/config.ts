import { z, ZodEffects } from "zod";
import { fromError } from 'zod-validation-error';
import yaml from 'js-yaml';
import camelcaseKeys from 'camelcase-keys';
import { CamelCasedPropertiesDeep } from 'type-fest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { exit } from "@src/utils/misc";
import { log } from "@src/utils/logger";

export const zodToCamelCase = <T extends z.ZodTypeAny>(zod: T): ZodEffects<z.ZodTypeAny, CamelCasedPropertiesDeep<T['_output']>> => {
    return zod.transform((val) => {
        return camelcaseKeys(val, {
            deep: true,
            stopPaths: ['env.shared', 'env.by_container']
        }) as CamelCasedPropertiesDeep<T>;
    });
};

const configSchema = zodToCamelCase(z.object({
    root_domain: z.string(),
    default_auth: z.string().refine((val) => typeof val !== 'string' || val.split(':').length === 2, {
        message: "Auth string should be in <user>:<password> format",
    }).transform(auth => {
        const [user, password] = auth.split(':');
        return { user, password };
    }),
    backup: z.object({
        password: z.string(),
        s3_endpoint: z.string(),
        s3_bucket: z.string(),
        s3_access_key: z.string(),
        s3_secret_key: z.string(),
    }).optional(),
    github: z.object({
        pat: z.string()
    }).optional(),
}));

export type SurekConfig = z.infer<typeof configSchema>;

export const loadConfig = (): SurekConfig => {
    const possibleFilenames = ["surek.yml", "surek.yaml"];
    const path = possibleFilenames.find(name => existsSync(join(process.cwd(), name)));
    if (!path) {
        return exit(`Config file not found. Make sure you have file surek.yml in current workign directory`);
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
    env: z.object({
        shared: z.array(z.string()).optional(),
        by_container: z.record(z.string(), z.array(z.string())).optional(),
    }).optional(),
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
};

export const exapndVariables = (val: string, config: SurekConfig) => {
    let result = val.replaceAll('<root>', config.rootDomain)
        .replaceAll('<default_auth>', config.defaultAuth.user + ':' + config.defaultAuth.password)
        .replaceAll('<default_user>', config.defaultAuth.user)
        .replaceAll('<default_password>', config.defaultAuth.password);
    if (config.backup) {
        result = result.replaceAll('<backup_password>', config.backup.password)
            .replaceAll('<backup_s3_endpoint>', config.backup.s3Endpoint)
            .replaceAll('<backup_s3_bucket>', config.backup.s3Bucket)
            .replaceAll('<backup_s3_access_key>', config.backup.s3AccessKey)
            .replaceAll('<backup_s3_secret_key>', config.backup.s3SecretKey);
    }
    return result;
};