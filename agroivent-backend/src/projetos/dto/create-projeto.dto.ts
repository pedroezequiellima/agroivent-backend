import { IsEnum, IsNumberString, IsString } from 'class-validator';
import { BiomaTipo, EstadoNordeste, RequerimentoTipo } from '../entities/projeto.entity';

export class CreateProjetoDto {
  @IsString()
  nomeProjeto: string;

  @IsEnum(EstadoNordeste)
  estado: EstadoNordeste;

  @IsEnum(BiomaTipo)
  bioma: BiomaTipo;

  @IsEnum(RequerimentoTipo)
  tipoRequerimento: RequerimentoTipo;

  @IsNumberString()
  areaTotalHa: string;

  @IsString()
  numeroArt: string;
}
