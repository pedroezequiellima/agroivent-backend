import { Column, Entity, JoinColumn, OneToOne, PrimaryColumn } from 'typeorm';
import { Projeto } from '../../projetos/entities/projeto.entity';

@Entity('estatisticas_projeto')
export class EstatisticasProjeto {
  @PrimaryColumn({ name: 'projeto_id', type: 'uuid' })
  projetoId: string;

  @OneToOne(() => Projeto, (projeto) => projeto.estatisticas, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'projeto_id' })
  projeto: Projeto;

  @Column({ name: 'erro_amostragem', type: 'decimal', precision: 10, scale: 2, nullable: true })
  erroAmostragem?: string;

  @Column({ type: 'decimal', precision: 4, scale: 2, default: 0.9 })
  probabilidade: string;

  @Column({ name: 'intensidade_amostral', type: 'int' })
  intensidadeAmostral: number;

  @Column({ name: 'media_volume_ha', type: 'decimal', precision: 10, scale: 4, nullable: true })
  mediaVolumeHa?: string;

  @Column({ type: 'decimal', precision: 15, scale: 8, nullable: true })
  variancia?: string;

  @Column({ name: 'desvio_padrao', type: 'decimal', precision: 15, scale: 8, nullable: true })
  desvioPadrao?: string;
}
