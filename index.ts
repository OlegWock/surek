#!/usr/bin/env node

import { app } from './src/commands.js';
import {run} from 'cmd-ts';

run(app, process.argv.slice(2));