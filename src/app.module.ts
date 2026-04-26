import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { AuthModule } from './auth/auth.module';
import { JwtAuthGuard } from './auth/guards/jwt-auth.guard';
import { databaseConfig } from './database/database.config';
import { PerfisModule } from './perfis/perfis.module';
import { EngineModule } from './engine/engine.module';
import { ProjetosModule } from './projetos/projetos.module';
import { InventarioModule } from './inventario/inventario.module';

@Module({
  imports: [
    // Carrega o .env globalmente
    ConfigModule.forRoot({ isGlobal: true }),

    // Configuração Assíncrona do Banco de Dados
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: async (configService: ConfigService) => {
        const databaseUrl = configService.getOrThrow<string>('DATABASE_URL');
        const isLocal = databaseUrl.includes('localhost') || databaseUrl.includes('127.0.0.1');

        return {
          type: 'postgres',
          url: databaseUrl,
          autoLoadEntities: true,
          synchronize: true, // Mantemos true para criar as tabelas no Supabase
          ssl: isLocal ? false : { rejectUnauthorized: false },
          extra: {
            ssl: isLocal ? undefined : { rejectUnauthorized: false },
            connectionTimeoutMillis: 10000,
          },
        };
      },
    }),

    AuthModule,
    PerfisModule,
    ProjetosModule,
    InventarioModule,
    EngineModule,
  ],
  controllers: [AppController],
  providers: [
    AppService,
    {
      provide: APP_GUARD,
      useClass: JwtAuthGuard,
    },
  ],
})
export class AppModule {}