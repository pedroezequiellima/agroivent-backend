import { Injectable, InternalServerErrorException } from '@nestjs/common';
import { spawn } from 'child_process';
import { join } from 'path';

@Injectable()
export class PythonService {
  executarProcessamento(
    arquivoPath: string,
    projetoId: string,
    opcoes?: {
      tipoInventario?: 'CENSO_100' | 'AMOSTRAGEM' | 'RCF';
      fatorForma?: number;
      fatorEmpilhamento?: number;
      areaTotalProjeto?: number;
      areaParcela?: number;
      dmc?: number;
    },
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      const scriptPath = join(process.cwd(), 'src', 'engine', 'scripts', 'main.py');
      const args = [
        scriptPath,
        '--arquivo',
        arquivoPath,
        '--projeto',
        projetoId,
        '--tipo_inventario',
        opcoes?.tipoInventario ?? 'AMOSTRAGEM',
        '--fator_forma',
        String(opcoes?.fatorForma ?? 0.7),
        '--fator_empilhamento',
        String(opcoes?.fatorEmpilhamento ?? 1.5),
        '--area_total_projeto',
        String(opcoes?.areaTotalProjeto ?? 1),
        '--area_parcela',
        String(opcoes?.areaParcela ?? 400),
        '--dmc',
        String(opcoes?.dmc ?? 50),
      ];
      const python = spawn('python', args);

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
