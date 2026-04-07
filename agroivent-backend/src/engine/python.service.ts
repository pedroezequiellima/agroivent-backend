import { Injectable, InternalServerErrorException } from '@nestjs/common';
import { spawn } from 'child_process';
import { join } from 'path';

@Injectable()
export class PythonService {
  executarProcessamento(arquivoPath: string, projetoId: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const scriptPath = join(process.cwd(), 'src', 'engine', 'scripts', 'main.py');
      const python = spawn('python', [scriptPath, '--arquivo', arquivoPath, '--projeto', projetoId]);

      let output = '';
      let errorOutput = '';

      python.stdout.on('data', (data: Buffer) => {
        output += data.toString();
      });

      python.stderr.on('data', (data: Buffer) => {
        errorOutput += data.toString();
      });

      python.on('close', (code) => {
        if (code !== 0) {
          reject(
            new InternalServerErrorException(
              `Falha no processamento Python: ${errorOutput || `codigo ${code}`}`,
            ),
          );
          return;
        }
        resolve(output.trim());
      });
    });
  }
}
