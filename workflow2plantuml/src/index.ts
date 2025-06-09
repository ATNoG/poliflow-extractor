import { MermaidDiagram, Specification } from '@severlessworkflow/sdk-typescript';
// import * as fs from 'fs';


async function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';

    process.stdin.setEncoding('utf8');

    process.stdin.on('data', (chunk) => {
      data += chunk;
    });

    process.stdin.on('end', () => {
      resolve(data.trim());
    });

    process.stdin.on('error', (err) => {
      reject(err);
    });
  });
}

// Top-level async function to run your logic
async function main() {
  const workflow = await readStdin();

  const graph = Specification.Workflow.fromSource(workflow);
  console.log(new MermaidDiagram(graph).sourceCode());
}

main().catch(console.error);
