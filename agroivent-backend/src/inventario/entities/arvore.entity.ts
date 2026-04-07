import { Column, Entity, JoinColumn, ManyToOne, PrimaryGeneratedColumn } from 'typeorm';
import { Projeto } from '../../projetos/entities/projeto.entity';

export enum SituacaoArvore {
  EXPLORAR = 'EXPLORAR',
  REMANESCENTE = 'REMANESCENTE',
  MATRIZ = 'MATRIZ',
  PROTEGIDA = 'PROTEGIDA',
}

@Entity('arvores')
export class Arvore {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'projeto_id', type: 'uuid' })
  projetoId: string;

  @ManyToOne(() => Projeto, (projeto) => projeto.arvores, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'projeto_id' })
  projeto: Projeto;

  @Column({ name: 'cap', type: 'decimal', precision: 10, scale: 2 })
  cap: string;

  @Column({ name: 'dap', type: 'decimal', precision: 10, scale: 2, nullable: true })
  dap?: string;

  @Column({ name: 'altura_comercial', type: 'decimal', precision: 10, scale: 2 })
  alturaComercial: string;

  @Column({ name: 'volume_m3', type: 'decimal', precision: 10, scale: 4, nullable: true })
  volumeM3?: string;

  @Column({ name: 'volume_estereo_st', type: 'decimal', precision: 10, scale: 4, nullable: true })
  volumeEstereoSt?: string;

  @Column({ name: 'qualidade_fuste', type: 'int', nullable: true })
  qualidadeFuste?: number;

  @Column({ name: 'coordenada_x', type: 'decimal', precision: 12, scale: 8, nullable: true })
  coordenadaX?: string;

  @Column({ name: 'coordenada_y', type: 'decimal', precision: 12, scale: 8, nullable: true })
  coordenadaY?: string;

  @Column({ type: 'enum', enum: SituacaoArvore, default: SituacaoArvore.REMANESCENTE })
  situacao: SituacaoArvore;
}
