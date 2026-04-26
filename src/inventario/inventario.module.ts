import { Module } from '@nestjs/common';
import { MulterModule } from '@nestjs/platform-express'; // <-- Importe isso
import { diskStorage } from 'multer'; // <-- E isso
import { TypeOrmModule } from '@nestjs/typeorm';
import { EngineModule } from '../engine/engine.module';
import { Projeto } from '../projetos/entities/projeto.entity';
import { Arvore } from './entities/arvore.entity';
import { EstatisticasProjeto } from './entities/estatisticas-projeto.entity';
import { InventarioController } from './inventario.controller';
import { InventarioService } from './inventario.service';
import { Especie } from './entities/especie.entity';

@Module({
  imports: [
    TypeOrmModule.forFeature([Projeto, Arvore, EstatisticasProjeto, Especie]),
    EngineModule,
    // Adicione esta configuração:
    MulterModule.register({
      storage: diskStorage({
        destination: './temp', // Pasta onde a planilha vai cair
        filename: (req, file, cb) => {
          cb(null, `${Date.now()}-${file.originalname}`);
        },
      }),
    }),
  ],
  controllers: [InventarioController],
  providers: [InventarioService],
})
export class InventarioModule {}
