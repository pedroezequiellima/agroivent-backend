import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  OneToMany,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { Arvore } from '../../inventario/entities/arvore.entity';
import { EstatisticasProjeto } from '../../inventario/entities/estatisticas-projeto.entity';
import { Perfil } from '../../perfis/entities/perfil.entity';

export enum EstadoNordeste {
  PE = 'PE',
  BA = 'BA',
  CE = 'CE',
  MA = 'MA',
  PI = 'PI',
  RN = 'RN',
  PB = 'PB',
  AL = 'AL',
  SE = 'SE',
}

export enum BiomaTipo {
  CAATINGA = 'CAATINGA',
  MATA_ATLANTICA = 'MATA_ATLANTICA',
  CERRADO = 'CERRADO',
  TRANSICAO = 'TRANSICAO',
}

export enum RequerimentoTipo {
  RCF = 'RCF',
  SUPRESSAO_PLENA = 'SUPRESSAO_PLENA',
  MANEJO_SUSTENTAVEL = 'MANEJO_SUSTENTAVEL',
}

export enum StatusProjeto {
  AGUARDANDO_PROCESSAMENTO = 'AGUARDANDO_PROCESSAMENTO',
  PROCESSANDO = 'PROCESSANDO',
  FINALIZADO = 'FINALIZADO',
  ERRO = 'ERRO',
}

@Entity('projetos')
export class Projeto {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'usuario_id', type: 'uuid' })
  usuarioId: string;

  @ManyToOne(() => Perfil, (perfil) => perfil.projetos, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'usuario_id' })
  usuario: Perfil;

  @Column({ name: 'nome_projeto', type: 'text' })
  nomeProjeto: string;

  @Column({ type: 'enum', enum: EstadoNordeste })
  estado: EstadoNordeste;

  @Column({ type: 'enum', enum: BiomaTipo })
  bioma: BiomaTipo;

  @Column({ name: 'tipo_requerimento', type: 'enum', enum: RequerimentoTipo })
  tipoRequerimento: RequerimentoTipo;

  @Column({ name: 'area_total_ha', type: 'decimal', precision: 10, scale: 2 })
  areaTotalHa: string;

  @Column({ name: 'numero_art', type: 'text' })
  numeroArt: string;

  @Column({ name: 'arquivo_bruto_url', type: 'text', nullable: true })
  arquivoBrutoUrl?: string;

  @Column({ type: 'enum', enum: StatusProjeto, default: StatusProjeto.AGUARDANDO_PROCESSAMENTO })
  status: StatusProjeto;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  @OneToMany(() => Arvore, (arvore) => arvore.projeto)
  arvores: Arvore[];

  @OneToOne(() => EstatisticasProjeto, (estatistica) => estatistica.projeto)
  estatisticas: EstatisticasProjeto;
}
